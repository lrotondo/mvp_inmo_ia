from __future__ import annotations

import re
from typing import Any

from app.catalog import get_properties_by_ids
from app.property_matching import _normalize_property_match_text

_LAST_LISTING_KEY = "last_listing"
_MAX_LISTING_ITEMS = 3

_OPTION_NUMBER_RE = re.compile(
    r"\b(?:opci[oó]n|la\s+opci[oó]n|el\s+de|la\s+de)\s*(?:n[°º]?\s*)?(\d+)\b",
    re.I,
)
_LA_N_RE = re.compile(r"\bla\s+(\d+)\b", re.I)
_ORDINAL_WORD_RE = re.compile(
    r"\b(?:la|el)?\s*(primera|segunda|tercera|cuarta|primer|segundo|tercer|cuarto)\b",
    re.I,
)
_ORDINAL_TO_INDEX: dict[str, int] = {
    "primera": 1,
    "primer": 1,
    "segunda": 2,
    "segundo": 2,
    "tercera": 3,
    "tercer": 3,
    "cuarta": 4,
    "cuarto": 4,
}
_TYPE_HINT_RE = re.compile(
    r"\b(duplex|d[uú]plex|departamento|depto|casa|ph)\b",
    re.I,
)


def merge_last_listing_into_capture(
    capture_data: dict[str, Any],
    *,
    property_ids: list[str],
    branch: str,
    catalog_path: str | None,
) -> dict[str, Any]:
    merged = dict(capture_data or {})
    ids = [str(pid).strip() for pid in property_ids if str(pid).strip()][: _MAX_LISTING_ITEMS]
    if not ids:
        return merged
    merged[_LAST_LISTING_KEY] = {
        "ids": ids,
        "branch": (branch or "").strip().lower(),
        "catalog_path": catalog_path,
    }
    return merged


def load_last_listing_rows(
    catalog_csv_path: str | None,
    capture_data: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    raw = (capture_data or {}).get(_LAST_LISTING_KEY)
    if not isinstance(raw, dict):
        return []
    ids = raw.get("ids") or []
    if not isinstance(ids, list):
        return []
    path = str(raw.get("catalog_path") or "").strip() or catalog_csv_path
    property_ids = [str(pid).strip() for pid in ids if str(pid).strip()]
    if not property_ids or not path:
        return []
    return get_properties_by_ids(path, property_ids, max_items=_MAX_LISTING_ITEMS)


def _row_search_blob(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("Titulo", "")),
        str(row.get("Tipo", "")),
        str(row.get("Direccion", "")),
        str(row.get("Barrio", "")),
        str(row.get("Caracteristicas", "")),
    ]
    return _normalize_property_match_text(" ".join(parts))


def _score_row_for_choice(user_norm: str, row: dict[str, Any]) -> int:
    blob = _row_search_blob(row)
    if not blob:
        return 0
    score = 0
    for hint in _TYPE_HINT_RE.findall(user_norm):
        key = _normalize_property_match_text(hint)
        if key in ("depto",):
            key = "departamento"
        if key in blob:
            score += 12
    tokens = [t for t in re.split(r"[^\wáéíóúñ]+", user_norm) if len(t) >= 4]
    for token in tokens:
        if token in blob:
            score += len(token)
    titulo = _normalize_property_match_text(str(row.get("Titulo", "")))
    if titulo and titulo in user_norm:
        score += len(titulo) + 5
    return score


def _listing_index_from_text(text: str) -> int | None:
    """Índice 1-based dentro del último listado (opción 2, la segunda, la 2)."""
    match = _OPTION_NUMBER_RE.search(text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    match = _LA_N_RE.search(text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    match = _ORDINAL_WORD_RE.search(text)
    if match:
        return _ORDINAL_TO_INDEX.get(match.group(1).lower())
    return None


def resolve_listing_choice_row(
    user_text: str,
    listing_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Elige una fila solo entre las del último listado enviado."""
    if not listing_rows:
        return None

    text = (user_text or "").strip()
    if not text:
        return None

    index = _listing_index_from_text(text)
    if index is not None and 1 <= index <= len(listing_rows):
        return listing_rows[index - 1]

    user_norm = _normalize_property_match_text(text)
    best: dict[str, Any] | None = None
    best_score = 0
    for row in listing_rows:
        score = _score_row_for_choice(user_norm, row)
        if score > best_score:
            best = row
            best_score = score

    if best_score >= 8:
        return best
    return None


def property_ref_from_listing_choice(
    user_text: str,
    listing_rows: list[dict[str, Any]],
) -> str:
    row = resolve_listing_choice_row(user_text, listing_rows)
    if row is None:
        return ""
    return str(row.get("ID", "")).strip()


def property_ref_from_listing_option_number(
    user_text: str,
    listing_rows: list[dict[str, Any]],
) -> str:
    index = _listing_index_from_text((user_text or "").strip())
    if index is None or index < 1 or index > len(listing_rows):
        return ""
    return str(listing_rows[index - 1].get("ID", "")).strip()
