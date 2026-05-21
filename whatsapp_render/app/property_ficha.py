from __future__ import annotations

import re
from typing import Any

from app.catalog import (
    gallery_photo_url,
    primary_photo_url,
    property_video_url,
)
from app.media_urls import is_likely_direct_image_url, is_social_or_page_url

_STRIP_BARE_URL_RE = re.compile(r"https?://\S+", re.I)
_INSTAGRAM_IN_TEXT_RE = re.compile(r"instagram\.com", re.I)
_GALERIA_LINK_RE = re.compile(
    r"\[(?:📸\s*)?(?:Ver\s+)?(?:galería\s+de\s+fotos|fotos|Foto)\]",
    re.I,
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
    for p in parts:
        if _INSTAGRAM_IN_TEXT_RE.search(p) or _STRIP_BARE_URL_RE.search(p):
            continue
        lines.append(f"• {p}")
    if len(lines) <= 1:
        return ""
    block = "\n".join(lines)
    if len(block) <= max_chars:
        return block
    return block[: max_chars - 3].rstrip() + "..."


def build_property_header_lines(
    row: dict[str, Any],
    *,
    option_index: int | None = None,
) -> list[str]:
    titulo = str(row.get("Titulo", "")).strip()
    direccion = str(row.get("Direccion", "")).strip()
    barrio = str(row.get("Barrio", "")).strip()
    ubicacion = direccion
    if barrio:
        ubicacion = f"{direccion}, {barrio}" if direccion else barrio

    precio = str(row.get("Precio", "")).strip()
    dormitorios = str(row.get("Dormitorios", "")).strip()
    ambientes = str(row.get("Ambientes", "")).strip()

    headline = titulo or ubicacion
    if option_index is not None:
        if headline:
            title = f"*Opción {option_index} — {headline}*"
        else:
            title = f"*Opción {option_index}*"
    elif headline:
        title = f"*{headline}*"
    else:
        title = ""

    detail_parts: list[str] = []
    if titulo and ubicacion and ubicacion.lower() != titulo.lower():
        detail_parts.append(ubicacion)
    if precio:
        detail_parts.append(
            f"Precio: ${precio}" if not precio.startswith("$") else f"Precio: {precio}"
        )
    if dormitorios:
        if "dormitorio" in dormitorios.lower():
            detail_parts.append(dormitorios)
        else:
            detail_parts.append(f"{dormitorios} dormitorios")
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


def build_detail_media_links_block(
    row: dict[str, Any],
    *,
    prefer_primary_preview: bool = True,
) -> str:
    primary = primary_photo_url(row)
    gallery = gallery_photo_url(row)
    video = property_video_url(row)
    lines: list[str] = []

    photo_link = ""
    external_gallery = ""

    if prefer_primary_preview:
        if is_likely_direct_image_url(primary):
            photo_link = primary
        elif is_likely_direct_image_url(gallery):
            photo_link = gallery
        elif gallery and not is_social_or_page_url(gallery):
            photo_link = gallery
        elif primary and not is_social_or_page_url(primary):
            photo_link = primary

        if gallery and gallery != photo_link and is_social_or_page_url(gallery):
            external_gallery = gallery
        elif (
            gallery
            and gallery != photo_link
            and not is_likely_direct_image_url(gallery)
        ):
            external_gallery = gallery
    else:
        fotos = gallery or primary
        if fotos:
            photo_link = fotos

    if photo_link and video:
        lines.append("Acá tenés todo el material visual de esta propiedad 👇")
        lines.append(f"[📸 Foto]({photo_link})")
        lines.append(f"[🎥 Video]({video})")
    elif photo_link:
        lines.append("¡Genial! Te dejo la galería completa 👇")
        lines.append(f"[📸 Fotos]({photo_link})")
    elif video:
        lines.append("Te comparto el video de la propiedad 👇")
        lines.append(f"[🎥 Video]({video})")

    if external_gallery:
        label = (
            "[📱 Ver galería en Instagram]({url})"
            if "instagram" in external_gallery.lower()
            else "[📱 Ver galería completa]({url})"
        )
        lines.append(label.format(url=external_gallery))

    tour = tour_360_url(row)
    if tour and not lines:
        lines.append("🔄 Recorré la propiedad en 360° 👇")
        lines.append(f"[🔄 Tour 360°]({tour})")
    elif tour and lines:
        lines.append(f"[🔄 Tour 360°]({tour})")

    if not lines:
        return ""
    return "\n".join(lines)


def text_mentions_row_header(text: str, row: dict[str, Any]) -> bool:
    """True si el texto ya nombra precio, título o dirección de la fila."""
    blob = (text or "").lower()
    if not blob.strip():
        return False

    precio = str(row.get("Precio", "")).strip()
    if precio:
        precio_digits = re.sub(r"\D", "", precio)
        text_digits = re.sub(r"\D", "", blob)
        if precio_digits and len(precio_digits) >= 4 and precio_digits in text_digits:
            return True

    for field in ("Titulo", "Direccion", "Barrio"):
        val = str(row.get(field, "")).strip().lower()
        if len(val) >= 5 and val in blob:
            return True
    return False


def _dedupe_consecutive_lines(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    prev_key = ""
    for line in lines:
        key = line.strip().lower()
        if key and key == prev_key:
            continue
        kept.append(line)
        prev_key = key
    return "\n".join(kept).strip()


def build_detail_delivery_caption(
    row: dict[str, Any],
    *,
    intro: str = "",
    tail: str = "",
    include_media_links: bool = True,
    caption_max_chars: int = 1024,
) -> str:
    """
    Un solo bloque para detalle de propiedad: comentario del bot + datos del catálogo
    sin repetir encabezado si el intro ya los menciona.
    """
    parts: list[str] = []
    intro_clean = _dedupe_consecutive_lines((intro or "").strip())
    if intro_clean:
        parts.append(intro_clean)

    if not text_mentions_row_header(intro_clean, row):
        parts.extend(build_property_header_lines(row, option_index=None))

    chars = format_caracteristicas_text(
        str(row.get("Caracteristicas", "")),
        max_chars=500 if include_media_links else 700,
    )
    if chars and not re.search(r"\*Características:\*", intro_clean, re.I):
        parts.append(chars)

    if include_media_links:
        body_so_far = "\n\n".join(parts)
        if not _GALERIA_LINK_RE.search(body_so_far):
            media = build_detail_media_links_block(row)
            if media:
                parts.append(media)

    if (tail or "").strip():
        parts.append(tail.strip())

    text = "\n\n".join(p for p in parts if p.strip())
    if len(text) <= caption_max_chars:
        return text
    return text[: caption_max_chars - 3].rstrip() + "..."


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
