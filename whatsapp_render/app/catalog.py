from __future__ import annotations

import csv
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
