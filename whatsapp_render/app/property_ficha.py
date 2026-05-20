from __future__ import annotations

from typing import Any

from app.catalog import (
    gallery_photo_url,
    primary_photo_url,
    property_video_url,
)


def tour_360_url(row: dict[str, Any]) -> str:
    return str(row.get("Tour_360") or row.get("Tour_360_URL") or "").strip()


def format_caracteristicas_text(raw: str, *, max_chars: int = 800) -> str:
    """Lista legible de Caracteristicas del catálogo."""
    text = (raw or "").strip()
    if not text:
        return ""
    parts = [p.strip() for p in text.split("|") if p.strip()]
    if not parts:
        return ""
    lines = ["*Características:*"]
    lines.extend(f"• {p}" for p in parts)
    block = "\n".join(lines)
    if len(block) <= max_chars:
        return block
    return block[: max_chars - 3].rstrip() + "..."


def build_property_header_lines(
    row: dict[str, Any],
    *,
    option_index: int | None = None,
) -> list[str]:
    direccion = str(row.get("Direccion", "")).strip()
    barrio = str(row.get("Barrio", "")).strip()
    ubicacion = direccion
    if barrio:
        ubicacion = f"{direccion}, {barrio}" if direccion else barrio

    precio = str(row.get("Precio", "")).strip()
    ambientes = str(row.get("Ambientes", "")).strip()

    if option_index is not None:
        title = f"*Opción {option_index} — {ubicacion}*" if ubicacion else f"*Opción {option_index}*"
    elif ubicacion:
        title = f"*{ubicacion}*"
    else:
        title = ""

    detail_parts: list[str] = []
    if precio:
        detail_parts.append(
            f"Precio: ${precio}" if not precio.startswith("$") else f"Precio: {precio}"
        )
    if ambientes:
        if "ambiente" in ambientes.lower():
            detail_parts.append(ambientes)
        else:
            detail_parts.append(f"{ambientes} ambientes")

    lines: list[str] = []
    if title:
        lines.append(title)
    if detail_parts:
        lines.append(" | ".join(detail_parts))
    return lines


def build_detail_media_links_block(row: dict[str, Any]) -> str:
    fotos = gallery_photo_url(row) or primary_photo_url(row)
    video = property_video_url(row)
    lines: list[str] = []

    if fotos and video:
        lines.append("Acá tenés todo el material visual de esta propiedad 👇")
        lines.append(f"[📸 Ver galería de fotos]({fotos})")
        lines.append(f"[🎥 Ver video]({video})")
    elif fotos:
        lines.append("¡Genial! Te dejo la galería completa 👇")
        lines.append(f"[📸 Ver galería de fotos]({fotos})")
    elif video:
        lines.append("Te comparto el video de la propiedad 👇")
        lines.append(f"[🎥 Ver video]({video})")

    tour = tour_360_url(row)
    if tour and not lines:
        lines.append("🔄 Recorré la propiedad en 360° 👇")
        lines.append(f"[🔄 Tour 360°]({tour})")
    elif tour and lines:
        lines.append(f"[🔄 Tour 360°]({tour})")

    if not lines:
        return ""
    return "\n".join(lines)


def build_property_ficha(
    row: dict[str, Any],
    *,
    include_media_links: bool = True,
    option_index: int | None = None,
    caption_max_chars: int = 1024,
) -> str:
    """Ficha unificada: encabezado + características + (opcional) galería/video."""
    parts: list[str] = []
    parts.extend(build_property_header_lines(row, option_index=option_index))

    chars = format_caracteristicas_text(
        str(row.get("Caracteristicas", "")),
        max_chars=600 if include_media_links else 800,
    )
    if chars:
        parts.append(chars)

    if include_media_links:
        media = build_detail_media_links_block(row)
        if media:
            parts.append(media)
    else:
        tour = tour_360_url(row)
        if tour:
            parts.append(f"🔄 Tour 360°: {tour}")

    text = "\n\n".join(p for p in parts if p.strip())
    if len(text) <= caption_max_chars:
        return text
    return text[: caption_max_chars - 3].rstrip() + "..."
