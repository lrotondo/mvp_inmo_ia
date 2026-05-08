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


def parse_money_from_precio(precio: str) -> float | None:
    text = re.sub(r"\s+", "", str(precio or ""))
    match = re.search(r"(?:usd|u\$s|\$)\s*([\d\.]+)", text, re.I)
    if not match:
        return None
    raw = match.group(1).replace(".", "").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    return value


def parse_ambientes(ambientes: str) -> int | None:
    match = re.search(r"(\d+)", str(ambientes or ""))
    return int(match.group(1)) if match else None


def filter_properties(user_text: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    q = (user_text or "").lower()
    hits = list(rows)

    if "tandil" in q:
        hits = [r for r in hits if "tandil" in str(r.get("Barrio", "")).lower()]
    if "rauch" in q:
        hits = [r for r in hits if "rauch" in str(r.get("Barrio", "")).lower()]

    amb_match = re.search(r"(\d+)\s*amb", q, re.I)
    if amb_match:
        target = int(amb_match.group(1))
        hits = [
            r
            for r in hits
            if parse_ambientes(str(r.get("Ambientes", ""))) == target
        ]

    max_match = re.search(
        r"(?:hasta|maximo|menos\s*de)\s*(?:usd|u\$s|\$)?\s*([\d\.]+)", q, re.I
    )
    if max_match:
        cap = float(max_match.group(1).replace(".", ""))

        def price_ok(row: Dict[str, Any]) -> bool:
            price = parse_money_from_precio(str(row.get("Precio", "")))
            if price is None:
                return True
            return price <= cap

        hits = [r for r in hits if price_ok(r)]

    return hits[:3]


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
