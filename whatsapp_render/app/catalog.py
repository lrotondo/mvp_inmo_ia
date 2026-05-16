from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_catalog_path(catalog_csv_path: str | None) -> Path:
    root = _project_root()
    if not catalog_csv_path or not str(catalog_csv_path).strip():
        return root / "data" / "propiedades_vivas.csv"
    p = Path(str(catalog_csv_path).strip())
    if p.is_absolute():
        return p
    return (root / p).resolve()


@lru_cache(maxsize=64)
def _load_properties_cached(resolved_path_str: str) -> tuple[dict[str, Any], ...]:
    path = Path(resolved_path_str)
    if not path.exists():
        return ()
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("ID"):
                rows.append(row)
    return tuple(rows)


def load_properties_for_catalog_path(catalog_csv_path: str | None) -> List[Dict[str, Any]]:
    path = resolve_catalog_path(catalog_csv_path)
    return list(_load_properties_cached(str(path.resolve())))


def load_properties() -> List[Dict[str, Any]]:
    return load_properties_for_catalog_path(None)


def format_catalog_compact(hits: List[Dict[str, Any]]) -> str:
    """Catálogo por fila con datos clave, características y link de fotos (cacheado vía get_cached_compact_catalog)."""
    lines = []
    for row in hits:
        tour = row.get("Tour_360") or row.get("Tour_360_URL") or ""
        tour_part = f" | Tour_360: {tour}" if str(tour).strip() else ""
        lines.append(
            "{ID} | {Direccion} | {Barrio} | {Precio} | {Ambientes} | "
            "Caracteristicas: {Caracteristicas} | Fotos: {Link_Fotos}{tour_part}".format(
                ID=row.get("ID", ""),
                Direccion=row.get("Direccion", ""),
                Barrio=row.get("Barrio", ""),
                Precio=row.get("Precio", ""),
                Ambientes=row.get("Ambientes", ""),
                Caracteristicas=row.get("Caracteristicas", ""),
                Link_Fotos=row.get("Link_Fotos", ""),
                tour_part=tour_part,
            )
        )
    return "\n".join(lines)


def format_catalog(hits: List[Dict[str, Any]]) -> str:
    lines = []
    for row in hits:
        lines.append(
            "ID {ID} | {Direccion} | {Barrio} | {Precio} | {Ambientes} | "
            "Caracteristicas: {Caracteristicas} | Fotos: {Link_Fotos}".format(
                ID=row.get("ID", ""),
                Direccion=row.get("Direccion", ""),
                Barrio=row.get("Barrio", ""),
                Precio=row.get("Precio", ""),
                Ambientes=row.get("Ambientes", ""),
                Caracteristicas=row.get("Caracteristicas", ""),
                Link_Fotos=row.get("Link_Fotos", ""),
            )
        )
    return "\n".join(lines)


@lru_cache(maxsize=64)
def _compact_catalog_cached(resolved_path_str: str) -> tuple[int, str]:
    rows = _load_properties_cached(resolved_path_str)
    text = format_catalog_compact(list(rows))
    if not text:
        return 0, "(catálogo vacío o no disponible.)"
    return len(rows), text


@lru_cache(maxsize=64)
def _catalog_search_terms_cached(resolved_path_str: str) -> frozenset[str]:
    terms: set[str] = set()
    for row in _load_properties_cached(resolved_path_str):
        for field in ("ID", "Direccion", "Barrio"):
            raw = str(row.get(field, "")).lower().strip()
            if not raw:
                continue
            terms.add(raw)
            for word in re.findall(r"[a-záéíóúñ0-9]{4,}", raw, flags=re.I):
                terms.add(word.lower())
    return frozenset(terms)


def get_cached_compact_catalog(
    catalog_csv_path: str | None,
) -> tuple[int, str]:
    """Cantidad de filas y texto compacto del catálogo (cacheado en memoria por ruta)."""
    path = resolve_catalog_path(catalog_csv_path)
    return _compact_catalog_cached(str(path.resolve()))


def get_catalog_search_terms(catalog_csv_path: str | None) -> frozenset[str]:
    path = resolve_catalog_path(catalog_csv_path)
    return _catalog_search_terms_cached(str(path.resolve()))


def get_catalog_for_flow(
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
) -> tuple[int, str]:
    """Catálogo según rama: compra -> venta CSV, alquiler -> rent CSV."""
    path = (flow_path or "").strip().lower()
    if path == "compra":
        return get_cached_compact_catalog(catalog_sale_path)
    if path == "alquiler":
        return get_cached_compact_catalog(catalog_rent_path)
    return 0, ""
