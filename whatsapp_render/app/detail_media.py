from __future__ import annotations

import logging
import re
from typing import Any

from app.catalog import (
    gallery_photo_url,
    get_property_row_by_ref,
    primary_photo_url,
    property_video_url,
)
from app.lead_context import extract_property_ref
from app.media_urls import detail_image_url, preview_link_for_text
from app.meta_client import (
    is_public_https_image_url,
    send_whatsapp_image_message,
    send_whatsapp_text_message,
)
from app.property_ficha import build_detail_media_links_block, build_property_ficha
from app.session_state import user_wants_fresh_start

logger = logging.getLogger(__name__)

_GALERIA_LINK_RE = re.compile(
    r"\[(?:📸\s*)?Ver\s+(?:galería\s+de\s+fotos|fotos)\](?:\([^)]+\))?",
    re.I,
)
_VIDEO_LINK_RE = re.compile(
    r"\[(?:🎥\s*)?Ver\s+video\](?:\([^)]+\))?",
    re.I,
)
_TOUR_LINK_RE = re.compile(
    r"\[(?:🔄\s*)?(?:Tour\s+360°|Ver\s+tour)\](?:\([^)]+\))?",
    re.I,
)
_LISTADO_TAG_RE = re.compile(r"\[LISTADO:", re.I)
_MEDIA_INTRO_RE = re.compile(
    r"^\s*(?:Acá tenés todo el material visual|Te dejo la galería|"
    r"Te comparto (?:el video|la galería)|¡Genial! Te dejo la galería|"
    r"Te paso el material visual|material visual completo)",
    re.I,
)

_DETAIL_REQUEST_RE = re.compile(
    r"\b("
    r"m[aá]s\s+info|contame\s+m[aá]s|cu[eé]ntame\s+m[aá]s|"
    r"detalles?|ampli[aá]|"
    r"(?:ver|mostr(?:ar|ame))\s+(?:las\s+)?fotos|"
    r"fotos?|videos?|"
    r"galer[ií]a|recorrido|tour\s*360"
    r")\b",
    re.I,
)

_OPTION_NUMBER_RE = re.compile(
    r"\bopci[oó]n\s*(?:n[°º]?\s*)?(\d+)\b",
    re.I,
)

_PROPERTY_INTEREST_RE = re.compile(
    r"\b("
    r"me\s+(?:gusta|interesa|cierra|convence)|"
    r"(?:la|el)\s+(?:opci[oó]n|de)\s*\d+|opci[oó]n\s*\d+|"
    r"esa\s+(?:me\s+)?(?:gusta|interesa)|"
    r"excelente\s+elecci[oó]n|buena\s+elecci[oó]n|"
    r"esa\s+propiedad|esta\s+propiedad|"
    r"quiero\s+(?:esa|esta|la\s+de)"
    r")\b",
    re.I,
)

_BOT_VISUAL_PROMISE_RE = re.compile(
    r"\b("
    r"material\s+visual|te\s+paso\s+(?:el\s+)?(?:material|fotos|video|galer[ií]a)|"
    r"te\s+(?:dejo|comparto)\s+(?:la\s+)?galer[ií]a|"
    r"galer[ií]a\s+completa|"
    r"conocela\s+mejor|conocerla\s+en\s+persona"
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


def user_showed_property_interest(current_user_text: str) -> bool:
    return bool(_PROPERTY_INTEREST_RE.search((current_user_text or "").strip()))


def bot_promises_visual_material(outbound_message: str) -> bool:
    return bool(_BOT_VISUAL_PROMISE_RE.search((outbound_message or "").strip()))


def _message_has_characteristics_block(text: str) -> bool:
    return bool(re.search(r"\*Características:\*", text or "", re.I))


def should_enrich_property_detail(
    *,
    outbound_message: str,
    current_user_text: str,
    flow_path: str,
) -> bool:
    """Ficha + material visual: detalle, elección de propiedad o promesa del bot."""
    path = (flow_path or "").strip().lower()
    if path in ("nuevo", "captacion"):
        return False
    if user_wants_fresh_start(current_user_text):
        return False

    body = (outbound_message or "").strip()
    if _LISTADO_TAG_RE.search(body):
        return False

    if user_requests_property_detail(current_user_text):
        return True
    if user_showed_property_interest(current_user_text):
        return True
    if bot_promises_visual_material(body):
        return True
    if message_offers_property_gallery(body) or message_offers_property_video(body):
        return (
            user_requests_property_detail(current_user_text)
            or user_showed_property_interest(current_user_text)
            or bot_promises_visual_material(body)
        )
    return False


def _property_ref_from_option_number(
    text: str,
    catalog_csv_path: str | None,
) -> str:
    """Resuelve 'opción 5' al ID de la fila en orden de catálogo (1-based)."""
    match = _OPTION_NUMBER_RE.search((text or "").strip())
    if not match:
        return ""
    from app.catalog import load_properties_for_catalog_path

    try:
        index = int(match.group(1))
    except ValueError:
        return ""
    if index < 1:
        return ""
    rows = load_properties_for_catalog_path(catalog_csv_path)
    if index > len(rows):
        return ""
    row_id = str(rows[index - 1].get("ID", "")).strip()
    return row_id


def property_ref_for_detail_enrich(
    *,
    current_user_text: str,
    outbound_message: str = "",
    history: list,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    fallback_ref: str = "",
    catalog_csv_path: str | None = None,
) -> str:
    """Referencia desde mensaje actual, respuesta del bot o historial (elección de propiedad)."""
    blobs: list[str] = []
    for part in (current_user_text, outbound_message):
        p = (part or "").strip()
        if p and p not in blobs:
            blobs.append(p)

    for blob in blobs:
        ref = extract_property_ref(
            "",
            flow_path=flow_path,
            catalog_sale_path=catalog_sale_path,
            catalog_rent_path=catalog_rent_path,
            history=[],
            current_user_text=blob,
            user_only=True,
        )
        if ref.strip():
            return ref.strip()
        opt_ref = _property_ref_from_option_number(blob, catalog_csv_path)
        if opt_ref:
            return opt_ref

    active_context = (
        user_requests_property_detail(current_user_text)
        or user_showed_property_interest(current_user_text)
        or bot_promises_visual_material(outbound_message)
        or user_requests_property_detail(outbound_message)
    )
    if active_context:
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
        for turn in reversed(history or []):
            if turn.role != "user":
                continue
            ref_turn = extract_property_ref(
                "",
                flow_path=flow_path,
                catalog_sale_path=catalog_sale_path,
                catalog_rent_path=catalog_rent_path,
                history=[],
                current_user_text=turn.content,
                user_only=True,
            )
            if ref_turn.strip():
                return ref_turn.strip()
            opt_ref = _property_ref_from_option_number(turn.content, catalog_csv_path)
            if opt_ref:
                return opt_ref

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


def _split_after_visual_intro(body: str) -> tuple[str, str]:
    """Separa texto previo al bloque visual y el resto (visitas, preguntas)."""
    lines = body.splitlines()
    before: list[str] = []
    after: list[str] = []
    passed_media = False
    for line in lines:
        stripped = line.strip()
        is_media = bool(
            _MEDIA_INTRO_RE.search(stripped)
            or _GALERIA_LINK_RE.search(stripped)
            or _VIDEO_LINK_RE.search(stripped)
            or _message_has_characteristics_block(stripped)
            or stripped.startswith("• ")
        )
        if is_media:
            passed_media = True
            continue
        if not passed_media:
            before.append(line)
        else:
            after.append(line)
    return "\n".join(before).strip(), "\n".join(after).strip()


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
    """Detalle / elección: ficha con características + links galería/video."""
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
            logger.info("detail_media: bloques omitidos (fuera de contexto)")
        return cleaned

    ref = property_ref_for_detail_enrich(
        current_user_text=current_user_text,
        outbound_message=body,
        history=history or [],
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        fallback_ref=property_ref,
        catalog_csv_path=catalog_csv_path,
    )
    if not ref:
        logger.warning(
            "detail_media: sin ref de propiedad (user=%r); mensaje sin inyectar",
            current_user_text[:80],
        )
        return body

    row = get_property_row_by_ref(catalog_csv_path, ref)
    if row is None:
        logger.warning("detail_media: ref=%r sin fila en catálogo", ref)
        return body

    if not _message_has_characteristics_block(body):
        merged = _merge_detail_ficha(body, row)
        logger.info("detail_media: ficha enriquecida id=%s", row.get("ID"))
        return merged

    if not message_offers_property_gallery(body):
        media = build_detail_media_links_block(row)
        if media.strip():
            logger.info("detail_media: links inyectados id=%s", row.get("ID"))
            return f"{body}\n\n{media}".strip()

    if message_offers_property_gallery(body) and not message_offers_property_video(body):
        video = property_video_url(row)
        if video:
            return (
                f"{body}\n\nTe dejo también el video 👇\n[🎥 Video]({video})"
            ).strip()

    return body


async def try_deliver_single_property_visual(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    message: str,
    catalog_csv_path: str | None,
    current_user_text: str,
    flow_path: str,
    history: list | None,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
    property_ref: str = "",
    graph_version: str | None = None,
) -> str | None:
    """
    Envía foto + texto (galería/video) cuando hay elección o promesa de material visual.
    Retorna texto consolidado para historial, o None para envío de texto único normal.
    """
    body = (message or "").strip()
    if not should_enrich_property_detail(
        outbound_message=body,
        current_user_text=current_user_text,
        flow_path=flow_path,
    ):
        return None

    ref = property_ref_for_detail_enrich(
        current_user_text=current_user_text,
        outbound_message=body,
        history=history or [],
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        fallback_ref=property_ref,
        catalog_csv_path=catalog_csv_path,
    )
    if not ref:
        return None

    row = get_property_row_by_ref(catalog_csv_path, ref)
    if row is None:
        return None

    if not message_offers_property_gallery(body):
        body = _merge_detail_ficha(body, row)

    intro_part = _split_detail_intro(body)
    _, tail_part = _split_after_visual_intro(body)
    media_block = build_detail_media_links_block(row)
    ficha_text = build_property_ficha(row, include_media_links=True, option_index=None)

    text_parts: list[str] = []
    if intro_part.strip():
        text_parts.append(intro_part.strip())
    if tail_part.strip() and (
        message_offers_property_gallery(tail_part) or message_offers_property_video(tail_part)
    ):
        text_parts.append(tail_part.strip())
    elif media_block.strip() and not message_offers_property_gallery(intro_part):
        text_parts.append(media_block.strip())
    elif not message_offers_property_gallery("\n\n".join(text_parts)):
        text_parts.append(ficha_text)
    followup_text = "\n\n".join(text_parts)

    primary = primary_photo_url(row)
    gallery = gallery_photo_url(row)
    photo = detail_image_url(primary, gallery)

    if photo and is_public_https_image_url(photo):
        caption = build_property_ficha(row, include_media_links=False, option_index=None)
        await send_whatsapp_image_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            image_url=photo,
            caption=caption,
            graph_version=graph_version,
        )
        if followup_text.strip():
            await send_whatsapp_text_message(
                access_token=access_token,
                phone_number_id=phone_number_id,
                to_wa_id=to_wa_id,
                message=followup_text,
                graph_version=graph_version,
                preview_url=False,
            )
        consolidated = "\n\n".join(
            p for p in (caption, followup_text) if p.strip()
        )
        logger.info("detail_media: imagen + texto id=%s", row.get("ID"))
        return consolidated

    outbound_text = followup_text.strip() or ficha_text
    preview_link = preview_link_for_text(primary, gallery)
    enable_preview = bool(preview_link)
    await send_whatsapp_text_message(
        access_token=access_token,
        phone_number_id=phone_number_id,
        to_wa_id=to_wa_id,
        message=outbound_text,
        graph_version=graph_version,
        preview_url=enable_preview,
    )
    logger.info("detail_media: solo texto con links id=%s", row.get("ID"))
    return outbound_text


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
