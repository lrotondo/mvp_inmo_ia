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
_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(\s*(https?://[^)\s]+)\s*\)",
    re.I,
)
_MEDIA_INTRO_RE = re.compile(
    r"material\s+visual|galer[ií]a\s+completa|te\s+paso\s+el\s+material",
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


def replace_markdown_links_with_labels(text: str) -> str:
    """
    [📸 Fotos](https://url-larga...) → 📸 Fotos (WhatsApp no renderiza markdown).
    La URL real va en el botón CTA al enviar.
    """

    def _repl(match: re.Match[str]) -> str:
        label = (match.group(1) or "").strip()
        return label if label else "Ver enlace"

    return _MARKDOWN_LINK_RE.sub(_repl, text or "")


def friendly_cta_label_for_url(url: str, *, kind: str = "") -> str:
    """Etiqueta corta con ícono para botón CTA (máx. 20 caracteres)."""
    u = (url or "").lower()
    k = (kind or "").lower()
    if k == "video" or "instagram.com/reel" in u or "/reel/" in u:
        return _cta_label("🎥 Video")
    if k == "tour" or "tour" in k or "360" in k:
        return _cta_label("🔄 Tour 360°")
    if k == "instagram" or "instagram.com" in u:
        return _cta_label("📱 Instagram")
    if k in ("album", "gallery", "fotos"):
        return _cta_label("📸 Fotos")
    if k == "photo" or k == "preview":
        return _cta_label("📸 Foto")
    return _cta_label("📸 Fotos")


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
    include_preview_cta: bool = False,
) -> list[MediaLinkButton]:
    """
    Botones CTA: álbum (url_link_fotos / Instagram), video, tour.
    foto_principal va en mensaje imagen; galería externa y video siempre como botón si existen.
    """
    primary = primary_photo_url(row).strip()
    gallery = gallery_photo_url(row).strip()
    video = property_video_url(row).strip()
    tour = tour_360_url(row).strip()

    _photo, external_gallery, video_url, tour_url = _resolve_media_urls(
        row, prefer_primary_preview=prefer_primary_preview
    )
    buttons: list[MediaLinkButton] = []
    seen_urls: set[str] = set()

    def _add(url: str, kind: str) -> None:
        u = (url or "").strip()
        if not u or u in seen_urls:
            return
        seen_urls.add(u)
        buttons.append(
            MediaLinkButton(friendly_cta_label_for_url(u, kind=kind), u)
        )

    if include_preview_cta and _photo:
        _add(_photo, "preview")

    if external_gallery:
        kind = "instagram" if "instagram" in external_gallery.lower() else "album"
        _add(external_gallery, kind)
    elif gallery and (
        gallery != primary
        or is_social_or_page_url(gallery)
        or not is_likely_direct_image_url(gallery)
    ):
        kind = "instagram" if "instagram" in gallery.lower() else "album"
        _add(gallery, kind)

    _add(video_url or video, "video")
    _add(tour_url or tour, "tour")

    if not buttons:
        for url, kind in (
            (gallery, "album"),
            (video, "video"),
            (tour, "tour"),
            (primary, "preview"),
        ):
            if url:
                _add(url, kind)
                break

    return buttons


def format_media_urls_text_fallback(row: dict[str, Any]) -> str:
    """Fallback si los botones CTA fallan: etiquetas + URLs con preview de WhatsApp."""
    buttons = collect_media_link_buttons(row, include_preview_cta=False)
    if not buttons:
        return ""
    lines = ["Material visual:"]
    for btn in buttons:
        lines.append(f"• {btn.label}: {btn.url}")
    return "\n".join(lines)


def build_detail_media_intro(
    row: dict[str, Any],
    *,
    prefer_primary_preview: bool = True,
) -> str:
    """Frase corta previa a los botones CTA (sin URLs en el texto)."""
    primary = primary_photo_url(row).strip()
    gallery = gallery_photo_url(row).strip()
    video = property_video_url(row).strip()
    tour = tour_360_url(row).strip()
    has_album = bool(gallery)
    has_preview = bool(primary)
    if (has_preview or has_album) and video:
        return "Acá tenés todo el material visual de esta propiedad 👇"
    if has_preview or has_album:
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
_VISIT_OR_HANDOFF_RE = re.compile(
    r"coordinar\s+una\s+visita|conocerla\s+en\s+persona|asesor\s+se\s+va\s+a\s+comunicar",
    re.I,
)
_LLM_PROPERTY_ESSAY_RE = re.compile(
    r"dormitorio|living\s+comedor|toilette|USD\s*[\d.,]+|precio\s+es\s+de|"
    r"piscina|calefacci[oó]n|porcelanato|lote\s+de\s+\d+",
    re.I,
)


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


def compact_detail_intro_for_row(
    intro: str,
    row: dict[str, Any],
    catalog_csv_path: str | None = None,
) -> str:
    """
    Intro breve para la ficha: sin párrafos largos del LLM (datos vienen del catálogo).
    """
    intro_clean = sanitize_detail_intro_for_row(intro, row, catalog_csv_path)
    if not intro_clean:
        return ""

    kept: list[str] = []
    for block in re.split(r"\n\s*\n", intro_clean):
        part = block.strip()
        if not part:
            continue
        if _CLOSING_QUESTION_RE.search(part) or _VISIT_OR_HANDOFF_RE.search(part):
            continue
        if _MEDIA_INTRO_RE.search(part) or _GALERIA_LINK_RE.search(part):
            continue
        if _CORRECTION_INTRO_RE.search(part):
            kept.append(part)
            continue
        if _LLM_PROPERTY_ESSAY_RE.search(part):
            continue
        if len(part) <= 160:
            kept.append(part)

    if kept:
        return "\n\n".join(kept)

    titulo = str(row.get("Titulo", "")).strip()
    direccion = str(row.get("Direccion", "")).strip()
    headline = titulo or direccion
    if headline:
        return f"¡Excelente elección! Te cuento sobre *{headline}*."
    return "¡Excelente elección! Te cuento sobre esta propiedad."


def extract_detail_tail(text: str) -> str:
    """Preguntas de cierre / visita al final de la respuesta del bot."""
    parts: list[str] = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        part = block.strip()
        if not part:
            continue
        if _CLOSING_QUESTION_RE.search(part) or _VISIT_OR_HANDOFF_RE.search(part):
            parts.append(part)
    return "\n\n".join(parts)


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
    include_media_links: bool = False,
    caption_max_chars: int = 1024,
    catalog_csv_path: str | None = None,
) -> str:
    """
    Caption de detalle: intro corto + datos del catálogo + pregunta de cierre.
    Fotos/video se envían aparte (imagen + botones CTA).
    """
    parts: list[str] = []
    intro_clean = compact_detail_intro_for_row(intro, row, catalog_csv_path)
    if intro_clean:
        parts.append(intro_clean)

    parts.extend(build_property_header_lines(row, option_index=None))

    chars = format_caracteristicas_text(
        str(row.get("Caracteristicas", "")),
        max_chars=700,
    )
    if chars:
        parts.append(chars)

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
