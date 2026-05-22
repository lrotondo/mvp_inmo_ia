from __future__ import annotations

from typing import Any


def build_document(row: dict[str, Any], branch: str) -> str:
    """Texto indexable para búsqueda semántica liviana."""
    path = (branch or "").strip().lower()
    parts = [
        str(row.get("Titulo", "")),
        str(row.get("Tipo", "")),
        str(row.get("Zona", "")),
        str(row.get("Lugar", "")),
        str(row.get("Barrio", "")),
        str(row.get("Direccion", "")),
        str(row.get("Dormitorios", "")),
        str(row.get("Características", "") or row.get("Caracteristicas", "")),
        str(row.get("Precio", "")),
    ]
    if path == "compra":
        parts.append("venta compra usd")
    else:
        parts.append("alquiler locacion ars mensual")
    return " ".join(p.strip() for p in parts if p and str(p).strip())
