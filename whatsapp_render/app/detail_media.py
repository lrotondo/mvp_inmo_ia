from __future__ import annotations

import logging
import re

from app.catalog import (
    gallery_photo_url,
    get_property_row_by_ref,
    primary_photo_url,
    property_video_url,
)

logger = logging.getLogger(__name__)

_GALERIA_LINK_RE = re.compile(
    r"\[(?:📸\s*)?Ver\s+(?:galería\s+de\s+fotos|fotos)\]",
    re.I,
)
_VIDEO_LINK_RE = re.compile(r"\[(?:🎥\s*)?Ver\s+video\]", re.I)
_LISTADO_TAG_RE = re.compile(r"\[LISTADO:", re.I)


def _detail_photo_url(row: dict[str, Any]) -> str:
    return gallery_photo_url(row) or primary_photo_url(row)


def build_detail_media_block(row: dict[str, Any]) -> str:
    """Bloque markdown de galería y/o video para modo detalle."""
    fotos = _detail_photo_url(row)
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

    if not lines:
        return ""
    return "\n".join(lines)


def message_offers_property_gallery(text: str) -> bool:
    return bool(_GALERIA_LINK_RE.search(text or ""))


def message_offers_property_video(text: str) -> bool:
    return bool(_VIDEO_LINK_RE.search(text or ""))


def ensure_detail_includes_video(
    message: str,
    *,
    catalog_csv_path: str | None,
    property_ref: str,
) -> str:
    """
    Si el mensaje ya ofrece galería/fotos en detalle y hay video en catálogo,
    agrega el link de video en el mismo mensaje cuando el LLM lo omitió.
    """
    body = (message or "").strip()
    if not body or _LISTADO_TAG_RE.search(body):
        return message
    if not message_offers_property_gallery(body):
        return message
    if message_offers_property_video(body):
        return message

    row = get_property_row_by_ref(catalog_csv_path, property_ref)
    if row is None:
        return message

    video = property_video_url(row)
    if not video:
        return message

    block = f"\n\nTe dejo también el video de la propiedad 👇\n[🎥 Ver video]({video})"
    logger.info(
        "detail_media: video agregado ref=%r id=%s",
        property_ref,
        row.get("ID"),
    )
    return body + block


def enrich_detail_media_from_catalog(
    message: str,
    *,
    catalog_csv_path: str | None,
    property_ref: str,
) -> str:
    """Asegura video en detalle; si hay fila y galería ausente, puede armar bloque completo."""
    body = (message or "").strip()
    if not body or _LISTADO_TAG_RE.search(body):
        return message

    row = get_property_row_by_ref(catalog_csv_path, property_ref)
    if row is None:
        return ensure_detail_includes_video(
            message,
            catalog_csv_path=catalog_csv_path,
            property_ref=property_ref,
        )

    has_gallery = message_offers_property_gallery(body)
    has_video = message_offers_property_video(body)
    fotos = _detail_photo_url(row)
    video = property_video_url(row)

    if has_gallery and not has_video and video:
        return ensure_detail_includes_video(
            message,
            catalog_csv_path=catalog_csv_path,
            property_ref=property_ref,
        )

    # Detalle con descripción pero sin bloque visual: insertar galería + video juntos
    if not has_gallery and not has_video and (fotos or video):
        block = build_detail_media_block(row)
        if block:
            logger.info(
                "detail_media: bloque visual agregado id=%s",
                row.get("ID"),
            )
            return f"{body}\n\n{block}"

    return message
