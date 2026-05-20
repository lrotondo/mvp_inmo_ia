from __future__ import annotations

import logging
import re
from typing import Any

from app.catalog import get_property_row_by_ref, property_video_url
from app.lead_context import extract_property_ref
from app.property_ficha import (
    build_detail_media_links_block,
    build_property_ficha,
)
from app.session_state import user_wants_fresh_start

logger = logging.getLogger(__name__)

_GALERIA_LINK_RE = re.compile(
    r"\[(?:📸\s*)?Ver\s+(?:galería\s+de\s+fotos|fotos)\]\([^)]+\)",
    re.I,
)
_VIDEO_LINK_RE = re.compile(
    r"\[(?:🎥\s*)?Ver\s+video\]\([^)]+\)",
    re.I,
)
_TOUR_LINK_RE = re.compile(
    r"\[(?:🔄\s*)?(?:Tour\s+360°|Ver\s+tour)\]\([^)]+\)",
    re.I,
)
_LISTADO_TAG_RE = re.compile(r"\[LISTADO:", re.I)
_MEDIA_INTRO_RE = re.compile(
    r"^\s*(?:Acá tenés todo el material visual|Te dejo la galería|"
    r"Te comparto el video|¡Genial! Te dejo la galería)",
    re.I,
)

_DETAIL_REQUEST_RE = re.compile(
    r"\b("
    r"m[aá]s\s+info|contame\s+m[aá]s|cu[eé]ntame\s+m[aá]s|"
    r"detalles?|ampli[aá]|"
    r"(?:ver|mostr(?:ar|ame))\s+(?:las\s+)?fotos|"
    r"galer[ií]a|video|recorrido|tour\s*360"
    r")\b",
    re.I,
)


def message_offers_property_gallery(text: str) -> bool:
    return bool(
        re.search(r"\[(?:📸\s*)?Ver\s+(?:galería\s+de\s+fotos|fotos)\]", text or "", re.I)
    )


def message_offers_property_video(text: str) -> bool:
    return bool(re.search(r"\[(?:🎥\s*)?Ver\s+video\]", text or "", re.I))


def user_requests_property_detail(current_user_text: str) -> bool:
    return bool(_DETAIL_REQUEST_RE.search((current_user_text or "").strip()))


def _message_has_characteristics_block(text: str) -> bool:
    return bool(re.search(r"\*Características:\*", text or "", re.I))


def should_enrich_property_detail(
    *,
    outbound_message: str,
    current_user_text: str,
    flow_path: str,
) -> bool:
    """
    Ficha con fotos/video solo en turno de detalle de UNA propiedad,
    nunca en triage, reinicio ni saludo genérico.
    """
    path = (flow_path or "").strip().lower()
    if path in ("nuevo", "captacion"):
        return False
    if user_wants_fresh_start(current_user_text):
        return False

    body = (outbound_message or "").strip()
    if _LISTADO_TAG_RE.search(body):
        return False

    # Links en la respuesta del LLM solo cuentan si el usuario pidió detalle en este turno
    if message_offers_property_gallery(body) or message_offers_property_video(body):
        return user_requests_property_detail(current_user_text)
    if user_requests_property_detail(current_user_text):
        return True
    return False


def property_ref_for_detail_enrich(
    *,
    current_user_text: str,
    history: list,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    fallback_ref: str = "",
) -> str:
    """Referencia solo del mensaje actual o, si pidió detalle, del historial reciente."""
    ref_now = extract_property_ref(
        "",
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        history=[],
        current_user_text=current_user_text,
        user_only=True,
    )
    if ref_now.strip():
        return ref_now.strip()

    if user_requests_property_detail(current_user_text):
        ref_hist = extract_property_ref(
            "",
            flow_path=flow_path,
            catalog_sale_path=catalog_sale_path,
            catalog_rent_path=catalog_rent_path,
            history=history,
            current_user_text=current_user_text,
            user_only=True,
        )
        if ref_hist.strip():
            return ref_hist.strip()

    return (fallback_ref or "").strip()


def strip_property_media_from_message(text: str) -> str:
    """Quita bloques de galería/video/características fuera de contexto de detalle."""
    if not (text or "").strip():
        return text

    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        if _GALERIA_LINK_RE.search(stripped) or _VIDEO_LINK_RE.search(stripped):
            continue
        if _TOUR_LINK_RE.search(stripped):
            continue
        if _MEDIA_INTRO_RE.search(stripped):
            continue
        if _message_has_characteristics_block(stripped):
            continue
        if stripped.startswith("• "):
            continue
        kept.append(line)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return cleaned or text.strip()


def _split_detail_intro(body: str) -> str:
    lines = body.splitlines()
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _GALERIA_LINK_RE.search(stripped) or _VIDEO_LINK_RE.search(stripped):
            break
        if _MEDIA_INTRO_RE.search(stripped):
            break
        if stripped.lower().startswith("*características"):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def _merge_detail_ficha(message: str, row: dict[str, Any]) -> str:
    intro = _split_detail_intro(message)
    ficha = build_property_ficha(row, include_media_links=True, option_index=None)
    if intro:
        return f"{intro}\n\n{ficha}".strip()
    return ficha


def enrich_detail_media_from_catalog(
    message: str,
    *,
    catalog_csv_path: str | None,
    property_ref: str,
    current_user_text: str = "",
    flow_path: str = "compra",
    history: list | None = None,
    catalog_sale_path: str | None = None,
    catalog_rent_path: str | None = None,
) -> str:
    """Detalle: ficha con características + galería/video solo cuando corresponde."""
    body = (message or "").strip()
    if not body:
        return message

    if not should_enrich_property_detail(
        outbound_message=body,
        current_user_text=current_user_text,
        flow_path=flow_path,
    ):
        cleaned = strip_property_media_from_message(body)
        if cleaned != body:
            logger.info("detail_media: bloques de propiedad omitidos (fuera de detalle)")
        return cleaned

    ref = property_ref_for_detail_enrich(
        current_user_text=current_user_text,
        history=history or [],
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        fallback_ref=property_ref,
    )
    if not ref:
        return strip_property_media_from_message(body)

    row = get_property_row_by_ref(catalog_csv_path, ref)
    if row is None:
        return body

    has_media_in_reply = message_offers_property_gallery(body) or message_offers_property_video(
        body
    )
    if not has_media_in_reply and not user_requests_property_detail(current_user_text):
        return body

    if not _message_has_characteristics_block(body):
        merged = _merge_detail_ficha(body, row)
        logger.info("detail_media: ficha detalle id=%s", row.get("ID"))
        return merged

    if has_media_in_reply and not message_offers_property_video(body):
        video_block = build_detail_media_links_block(row)
        if "Ver video" in video_block and property_video_url(row):
            return f"{body}\n\nTe dejo también el video 👇\n[🎥 Ver video]({property_video_url(row)})"

    return body


def ensure_detail_includes_video(
    message: str,
    *,
    catalog_csv_path: str | None,
    property_ref: str,
    current_user_text: str = "",
    flow_path: str = "compra",
    **kwargs: Any,
) -> str:
    return enrich_detail_media_from_catalog(
        message,
        catalog_csv_path=catalog_csv_path,
        property_ref=property_ref,
        current_user_text=current_user_text,
        flow_path=flow_path,
        **kwargs,
    )
