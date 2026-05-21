from __future__ import annotations

import re
from dataclasses import dataclass
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


_CTA_LABEL_MAX = 20


@dataclass(frozen=True)
class MediaLinkButton:
    label: str
    url: str


def _cta_label(text: str) -> str:
    return text.strip()[:_CTA_LABEL_MAX]


def _resolve_media_urls(
    row: dict[str, Any],
    *,
    prefer_primary_preview: bool = True,
) -> tuple[str, str, str, str]:
    """photo_link, external_gallery, video, tour."""
    primary = primary_photo_url(row)
    gallery = gallery_photo_url(row)
    video = property_video_url(row)
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

    return photo_link, external_gallery, video, tour_360_url(row)


def collect_media_link_buttons(
    row: dict[str, Any],
    *,
    prefer_primary_preview: bool = True,
) -> list[MediaLinkButton]:
    """Enlaces para botones CTA de WhatsApp (URL oculta en el botón)."""
    photo_link, external_gallery, video, tour = _resolve_media_urls(
        row, prefer_primary_preview=prefer_primary_preview
    )
    buttons: list[MediaLinkButton] = []

    if photo_link:
        buttons.append(MediaLinkButton(_cta_label("📸 Ver fotos"), photo_link))
    if video:
        buttons.append(MediaLinkButton(_cta_label("🎥 Ver video"), video))
    if external_gallery:
        label = (
            "📱 Ver Instagram"
            if "instagram" in external_gallery.lower()
            else "📱 Ver galería"
        )
        buttons.append(MediaLinkButton(_cta_label(label), external_gallery))
    if tour:
        buttons.append(MediaLinkButton(_cta_label("🔄 Tour 360°"), tour))

    return buttons


def build_detail_media_intro(
    row: dict[str, Any],
    *,
    prefer_primary_preview: bool = True,
) -> str:
    """Frase corta previa a los botones CTA (sin URLs en el texto)."""
    photo_link, external_gallery, video, tour = _resolve_media_urls(
        row, prefer_primary_preview=prefer_primary_preview
    )
    has_photo = bool(photo_link or external_gallery)
    if has_photo and video:
        return "Acá tenés todo el material visual de esta propiedad 👇"
    if has_photo:
        return "¡Genial! Te dejo la galería completa 👇"
    if video:
        return "Te comparto el video de la propiedad 👇"
    if tour:
        return "🔄 Recorré la propiedad en 360° 👇"
    return ""


def format_media_buttons_for_history(buttons: list[MediaLinkButton]) -> str:
    if not buttons:
        return ""
    lines = ["Material visual:"]
    for btn in buttons:
        lines.append(f"• {btn.label}")
    return "\n".join(lines)


def build_detail_media_links_block(
    row: dict[str, Any],
    *,
    prefer_primary_preview: bool = True,
) -> str:
    """Solo intro; los links van en botones CTA al enviar por WhatsApp."""
    return build_detail_media_intro(row, prefer_primary_preview=prefer_primary_preview)


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


_CORRECTION_INTRO_RE = re.compile(
    r"disculp|me confund|vamos de nuevo|informaci[oó]n correcta|de nuevo con",
    re.I,
)
_CLOSING_QUESTION_RE = re.compile(r"\?\s*$|¿.+", re.M)


def intro_conflicts_with_catalog_row(
    intro: str,
    row: dict[str, Any],
    catalog_csv_path: str | None,
) -> bool:
    """True si el intro describe otra fila del catálogo, no la resuelta."""
    if text_mentions_row_header(intro, row):
        return False
    intro_norm = (intro or "").lower()
    if not intro_norm.strip():
        return False

    from app.catalog import iter_rows_for_property_matching

    row_id = str(row.get("ID", "")).strip()
    for other in iter_rows_for_property_matching(catalog_csv_path):
        if str(other.get("ID", "")).strip() == row_id:
            continue
        for field in ("Titulo", "Direccion"):
            val = str(other.get(field, "")).strip().lower()
            if len(val) >= 8 and val in intro_norm:
                return True
    return False


def sanitize_detail_intro_for_row(
    intro: str,
    row: dict[str, Any],
    catalog_csv_path: str | None = None,
) -> str:
    """
    Quita del intro del LLM descripciones de otra propiedad; conserva disculpas y preguntas.
    """
    intro_clean = _dedupe_consecutive_lines((intro or "").strip())
    if not intro_clean:
        return ""

    if not intro_conflicts_with_catalog_row(intro_clean, row, catalog_csv_path):
        return intro_clean

    kept: list[str] = []
    for block in re.split(r"\n\s*\n", intro_clean):
        part = block.strip()
        if not part:
            continue
        if text_mentions_row_header(part, row):
            kept.append(part)
            continue
        if _CORRECTION_INTRO_RE.search(part):
            kept.append(part)
            continue
        if _CLOSING_QUESTION_RE.search(part):
            kept.append(part)
            continue

    if kept:
        return "\n\n".join(kept)

    titulo = str(row.get("Titulo", "")).strip()
    direccion = str(row.get("Direccion", "")).strip()
    headline = titulo or direccion
    if headline:
        return f"Te cuento sobre *{headline}* 👇"
    return "Te comparto la información de esta propiedad 👇"


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
    catalog_csv_path: str | None = None,
) -> str:
    """
    Un solo bloque para detalle de propiedad: comentario del bot + datos del catálogo
    sin repetir encabezado si el intro ya los menciona.
    """
    parts: list[str] = []
    intro_clean = sanitize_detail_intro_for_row(intro, row, catalog_csv_path)
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
            intro = build_detail_media_intro(row)
            if intro:
                parts.append(intro)

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
