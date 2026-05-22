from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_AVAILABLE_VALUES = frozenset(
    {"si", "sí", "s", "yes", "y", "1", "true", "verdadero", "x", "disponible"}
)

from app.catalog_profiles import (
    format_catalog_compact_for_branch,
    match_fields_for_branch,
    search_fields_for_branch,
)
from app.catalog_sources import (
    CatalogRef,
    fetch_rows,
    is_google_sheet_ref,
    parse_catalog_ref,
    resolve_csv_path,
)

_DEFAULT_CACHE_TTL = 300
_cache_lock = Lock()
_rows_cache: dict[str, tuple[float, tuple[dict[str, Any], ...]]] = {}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _cache_ttl_seconds() -> int:
    raw = os.environ.get("CATALOG_CACHE_TTL_SECONDS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return _DEFAULT_CACHE_TTL


def _default_catalog_ref() -> CatalogRef:
    path = str((_project_root() / "data" / "propiedades_vivas.csv").resolve())
    return CatalogRef(kind="csv", raw=path, csv_path=path)


def _ref_for_path(catalog_path: str | None) -> CatalogRef:
    ref = parse_catalog_ref(catalog_path)
    return ref if ref is not None else _default_catalog_ref()


def _file_mtime_ns(resolved_path: Path) -> int:
    if not resolved_path.exists():
        return 0
    return resolved_path.stat().st_mtime_ns


def _load_rows(ref: CatalogRef) -> tuple[dict[str, Any], ...]:
    cache_key = ref.cache_key()
    now = time.monotonic()
    ttl = _cache_ttl_seconds()

    if ref.kind == "csv":
        path = resolve_csv_path(ref.csv_path or ref.raw)
        mtime_ns = _file_mtime_ns(path)
        cache_key = f"{cache_key}:{mtime_ns}"

    with _cache_lock:
        cached = _rows_cache.get(cache_key)
        if cached is not None:
            loaded_at, rows = cached
            if ref.kind == "google_sheet" and (now - loaded_at) < ttl:
                return rows
            if ref.kind == "csv":
                return rows

    rows_tuple = tuple(fetch_rows(ref))

    with _cache_lock:
        _rows_cache[cache_key] = (now, rows_tuple)
        if len(_rows_cache) > 128:
            oldest = min(_rows_cache.items(), key=lambda item: item[1][0])
            _rows_cache.pop(oldest[0], None)

    return rows_tuple


def resolve_catalog_path(catalog_csv_path: str | None) -> Path:
    ref = _ref_for_path(catalog_csv_path)
    if ref.kind == "google_sheet":
        return _project_root() / "data" / "propiedades_vivas.csv"
    return resolve_csv_path(ref.csv_path or ref.raw)


def resolve_rent_catalog_path(
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
) -> str | None:
    """Ruta o ref de alquiler: explícita en tenant; convención _alquiler.csv solo para CSV."""
    explicit = (catalog_rent_path or "").strip()
    if explicit:
        return explicit

    sale = (catalog_sale_path or "").strip()
    if not sale:
        return None

    if is_google_sheet_ref(sale):
        return None

    sale_resolved = resolve_csv_path(sale)
    candidate = sale_resolved.parent / f"{sale_resolved.stem}_alquiler.csv"
    if not candidate.exists():
        return None
    root = _project_root()
    try:
        return str(candidate.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(candidate)


def is_property_available(row: dict[str, Any]) -> bool:
    raw = str(row.get("Disponible", "")).strip().lower()
    return raw in _AVAILABLE_VALUES


def _catalog_has_disponible_column(rows: list[dict[str, Any]]) -> bool:
    return any(str(row.get("Disponible", "")).strip() for row in rows)


def load_properties_for_catalog_path(catalog_csv_path: str | None) -> List[Dict[str, Any]]:
    ref = _ref_for_path(catalog_csv_path)
    all_rows = list(_load_rows(ref))
    if not all_rows:
        return []
    if not _catalog_has_disponible_column(all_rows):
        return all_rows
    available = [row for row in all_rows if is_property_available(row)]
    if len(available) < len(all_rows):
        logger.debug(
            "catalog_availability path=%r total=%s available=%s",
            catalog_csv_path,
            len(all_rows),
            len(available),
        )
    return available


def iter_rows_for_property_matching(
    catalog_csv_path: str | None,
) -> list[dict[str, Any]]:
    """Filas usables para resolver dirección/ID (misma regla que get_properties_by_ids)."""
    ref = _ref_for_path(catalog_csv_path)
    return [row for row in _load_rows(ref) if _row_available_for_id_lookup(row)]


def load_properties() -> List[Dict[str, Any]]:
    return load_properties_for_catalog_path(None)


def _normalize_property_id(raw: str) -> str:
    return str(raw or "").strip()


def _row_available_for_id_lookup(row: dict[str, Any]) -> bool:
    """Lookup por [LISTADO:ids]: sin columna Disponible = incluir (CSV legacy)."""
    raw = str(row.get("Disponible", "")).strip().lower()
    if not raw:
        return True
    return is_property_available(row)


def get_properties_by_ids(
    catalog_csv_path: str | None,
    property_ids: list[str],
    *,
    max_items: int = 3,
) -> list[dict[str, Any]]:
    """Filas por ID en orden del tag [LISTADO:...] (excluye Disponible explícito no)."""
    wanted = [_normalize_property_id(pid) for pid in property_ids if _normalize_property_id(pid)]
    if not wanted:
        return []
    if max_items > 0:
        wanted = wanted[:max_items]

    ref = _ref_for_path(catalog_csv_path)
    by_id: dict[str, dict[str, Any]] = {}
    for row in _load_rows(ref):
        if not _row_available_for_id_lookup(row):
            continue
        key = _normalize_property_id(str(row.get("ID", "")))
        if key and key not in by_id:
            by_id[key] = row

    ordered: list[dict[str, Any]] = []
    for pid in wanted:
        row = by_id.get(pid)
        if row is not None:
            ordered.append(row)
    return ordered


def primary_photo_url(row: dict[str, Any]) -> str:
    """Foto del resumen/listado (columna foto_principal; legacy Link_Fotos)."""
    return str(row.get("foto_principal") or row.get("Link_Fotos") or "").strip()


def gallery_photo_url(row: dict[str, Any]) -> str:
    """Carrusel / galería al pedir detalle (columna url_link_fotos)."""
    return str(row.get("url_link_fotos") or "").strip()


def property_video_url(row: dict[str, Any]) -> str:
    return str(row.get("url_link_video") or "").strip()


def _normalize_match_text(text: str) -> str:
    from app.lead_context import _normalize_property_match_text

    return _normalize_property_match_text((text or "").lower())


def field_matches_reference(reference_norm: str, field_value: str) -> bool:
    """True si la referencia (ej. 'los nogales') coincide con un campo del catálogo."""
    val = _normalize_match_text(field_value)
    if len(val) < 4 or len(reference_norm) < 4:
        return False
    if val in reference_norm or reference_norm in val:
        return True
    tokens = [t for t in re.findall(r"[a-záéíóúñ0-9]{4,}", val)]
    if not tokens:
        return False
    hits = [t for t in tokens if t in reference_norm]
    if len(tokens) == 1:
        return bool(hits)
    if len(hits) >= min(2, len(tokens)):
        return True
    # Dirección compuesta: un token distintivo alcanza (ej. "nogales" sin "tilos").
    return any(len(t) >= 5 and t in reference_norm for t in tokens)


def _all_match_fields() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            match_fields_for_branch("compra") + match_fields_for_branch("alquiler")
        )
    )


def find_property_row_for_user_text(
    catalog_csv_path: str | None,
    text: str,
    *,
    branch: str | None = None,
    rows_scope: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Mejor fila cuyo título/dirección/ubicación coincide con el texto del usuario."""
    blob_norm = _normalize_match_text(text)
    if len(blob_norm) < 4:
        return None

    if rows_scope is not None:
        rows_iter: list[dict[str, Any]] = rows_scope
    else:
        rows_iter = list(_load_rows(_ref_for_path(catalog_csv_path)))

    fields = (
        match_fields_for_branch(branch)
        if branch
        else _all_match_fields()
    )

    best: dict[str, Any] | None = None
    best_len = 0
    for row in rows_iter:
        if rows_scope is None and not _row_available_for_id_lookup(row):
            continue
        for field in fields:
            val = str(row.get(field, "")).strip()
            if not field_matches_reference(blob_norm, val):
                continue
            if len(val) > best_len:
                best = row
                best_len = len(val)
    return best


def get_property_row_by_ref(
    catalog_csv_path: str | None,
    property_ref: str,
) -> dict[str, Any] | None:
    """Busca fila por ID, 'ID x' o coincidencia en dirección/barrio/título."""
    ref = _normalize_property_id(property_ref)
    if not ref:
        return None

    id_candidate = ref
    if id_candidate.lower().startswith("id "):
        id_candidate = id_candidate[3:].strip()

    by_id = get_properties_by_ids(catalog_csv_path, [id_candidate], max_items=1)
    if by_id:
        return by_id[0]

    ref_norm = _normalize_match_text(ref)
    best: dict[str, Any] | None = None
    best_len = 0
    catalog_ref = _ref_for_path(catalog_csv_path)
    for row in _load_rows(catalog_ref):
        if not _row_available_for_id_lookup(row):
            continue
        for field in _all_match_fields():
            val = str(row.get(field, "")).strip()
            if not field_matches_reference(ref_norm, val):
                continue
            if len(val) > best_len:
                best = row
                best_len = len(val)
    return best


def _media_suffix_parts(row: dict[str, Any]) -> str:
    parts: list[str] = []
    principal = primary_photo_url(row)
    if principal:
        parts.append(f"foto_principal: {principal}")
    galeria = gallery_photo_url(row)
    if galeria:
        parts.append(f"url_link_fotos: {galeria}")
    video = str(row.get("url_link_video", "")).strip()
    if video:
        parts.append(f"Video: {video}")
    tour = str(row.get("Tour_360") or row.get("Tour_360_URL") or "").strip()
    if tour:
        parts.append(f"Tour_360: {tour}")
    if not parts:
        return ""
    return " | " + " | ".join(parts)


def format_catalog_compact(
    hits: List[Dict[str, Any]],
    *,
    branch: str = "compra",
) -> str:
    """Compat: delega al formateador por rama."""
    return format_catalog_compact_for_branch(hits, branch)


def format_catalog(
    hits: List[Dict[str, Any]],
    *,
    branch: str = "compra",
) -> str:
    return format_catalog_compact_for_branch(hits, branch)


def get_cached_compact_catalog(
    catalog_csv_path: str | None,
    *,
    branch: str = "compra",
) -> tuple[int, str]:
    rows = load_properties_for_catalog_path(catalog_csv_path)
    text = format_catalog_compact_for_branch(rows, branch)
    if not text:
        return 0, "(catálogo vacío o no disponible.)"
    return len(rows), text


def get_catalog_search_terms(
    catalog_csv_path: str | None,
    *,
    branch: str = "compra",
) -> frozenset[str]:
    terms: set[str] = set()
    for row in load_properties_for_catalog_path(catalog_csv_path):
        for field in search_fields_for_branch(branch):
            raw = str(row.get(field, "")).lower().strip()
            if not raw:
                continue
            terms.add(raw)
            for word in re.findall(r"[a-záéíóúñ0-9]{4,}", raw, flags=re.I):
                terms.add(word.lower())
    return frozenset(terms)


def get_catalog_for_flow(
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
) -> tuple[int, str, str | None]:
    branch = (flow_path or "").strip().lower()
    if branch == "compra":
        used = (catalog_sale_path or "").strip() or None
        count, block = get_cached_compact_catalog(catalog_sale_path, branch="compra")
        return count, block, used
    if branch == "alquiler":
        used = resolve_rent_catalog_path(catalog_sale_path, catalog_rent_path)
        count, block = get_cached_compact_catalog(used, branch="alquiler")
        return count, block, used
    return 0, "", None
