from __future__ import annotations

from typing import Any, Literal

CatalogBranch = Literal["compra", "alquiler"]

# (clave en row dict, etiqueta visible al LLM)
SALE_COMPACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("ID", "ID"),
    ("Titulo", "Titulo"),
    ("Tipo", "Tipo"),
    ("Direccion", "Direccion"),
    ("Lugar", "Lugar"),
    ("Zona", "Zona"),
    ("Precio", "Precio USD"),
    ("Dormitorios", "Dormitorios"),
    ("Ambientes", "Ambientes"),
    ("Caracteristicas", "Caracteristicas"),
)

RENT_COMPACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("ID", "ID"),
    ("Titulo", "Titulo"),
    ("Tipo", "Tipo"),
    ("Direccion", "Direccion"),
    ("Barrio", "Barrio"),
    ("Precio", "Precio mensual ARS"),
    ("Expensas", "Expensas ARS"),
    ("Garantia_Propietaria", "Garantia"),
    ("Seguro_Caucion", "Seguro caucion"),
    ("Admite_mascotas", "Mascotas"),
    ("Ajuste_IPC", "Ajuste IPC"),
    ("Dormitorios", "Dormitorios"),
    ("Ambientes", "Ambientes"),
    ("Caracteristicas", "Caracteristicas"),
)

SALE_SEARCH_FIELDS: tuple[str, ...] = (
    "ID",
    "Titulo",
    "Tipo",
    "Direccion",
    "Lugar",
    "Zona",
    "Dormitorios",
)

RENT_SEARCH_FIELDS: tuple[str, ...] = (
    "ID",
    "Titulo",
    "Tipo",
    "Direccion",
    "Barrio",
    "Dormitorios",
)

SALE_MATCH_FIELDS: tuple[str, ...] = (
    "Titulo",
    "Tipo",
    "Direccion",
    "Lugar",
    "Zona",
)

RENT_MATCH_FIELDS: tuple[str, ...] = (
    "Titulo",
    "Tipo",
    "Direccion",
    "Barrio",
)


def normalize_catalog_branch(flow_path: str) -> CatalogBranch | None:
    path = (flow_path or "").strip().lower()
    if path == "compra":
        return "compra"
    if path == "alquiler":
        return "alquiler"
    return None


def compact_fields_for_branch(branch: str) -> tuple[tuple[str, str], ...]:
    if normalize_catalog_branch(branch) == "alquiler":
        return RENT_COMPACT_FIELDS
    return SALE_COMPACT_FIELDS


def search_fields_for_branch(branch: str) -> tuple[str, ...]:
    if normalize_catalog_branch(branch) == "alquiler":
        return RENT_SEARCH_FIELDS
    return SALE_SEARCH_FIELDS


def match_fields_for_branch(branch: str) -> tuple[str, ...]:
    if normalize_catalog_branch(branch) == "alquiler":
        return RENT_MATCH_FIELDS
    return SALE_MATCH_FIELDS


def _media_flags(row: dict[str, Any]) -> str:
    flags: list[str] = []
    if str(row.get("foto_principal") or row.get("Link_Fotos") or "").strip():
        flags.append("tiene_foto")
    if str(row.get("url_link_fotos") or "").strip():
        flags.append("tiene_album")
    if str(row.get("url_link_video") or "").strip():
        flags.append("tiene_video")
    if str(row.get("Tour_360") or row.get("Tour_360_URL") or "").strip():
        flags.append("tiene_tour")
    if not flags:
        return ""
    return "media: " + ", ".join(flags)


def format_row_compact(row: dict[str, Any], branch: str) -> str:
    """Una fila del catálogo para el LLM, con campos nativos de la rama."""
    parts: list[str] = []
    for key, label in compact_fields_for_branch(branch):
        val = str(row.get(key, "")).strip()
        if not val:
            continue
        parts.append(f"{label}: {val}")

    if normalize_catalog_branch(branch) == "alquiler":
        media = _media_flags(row)
        if media:
            parts.append(media)

    return " | ".join(parts)


def format_catalog_compact_for_branch(
    hits: list[dict[str, Any]],
    branch: str,
) -> str:
    lines = [format_row_compact(row, branch) for row in hits]
    return "\n".join(line for line in lines if line.strip())


def format_sale_compact(hits: list[dict[str, Any]]) -> str:
    return format_catalog_compact_for_branch(hits, "compra")


def format_rent_compact(hits: list[dict[str, Any]]) -> str:
    return format_catalog_compact_for_branch(hits, "alquiler")
