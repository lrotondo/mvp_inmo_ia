from __future__ import annotations

import logging
import re
from typing import Any

from app.catalog import (
    find_property_row_for_user_text,
    gallery_photo_url,
    get_properties_by_ids,
    get_property_row_by_ref,
    primary_photo_url,
    property_video_url,
)
from app.lead_context import extract_property_ref, user_search_profile_ready
from app.media_urls import detail_image_url
from app.meta_client import (
    is_public_https_image_url,
    send_whatsapp_cta_url_message,
    send_whatsapp_image_message,
    send_whatsapp_text_message,
)
from app.property_ficha import (
    build_detail_delivery_caption,
    build_detail_media_intro,
    collect_media_link_buttons,
    extract_detail_tail,
    format_media_buttons_for_history,
    format_media_urls_text_fallback,
    replace_markdown_links_with_labels,
)
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
_LISTADO_IDS_RE = re.compile(r"\[LISTADO:\s*([^\]]+)\]", re.I)
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
_MISSING_MEDIA_RE = re.compile(
    r"\b("
    r"no\s+veo\s+(?:las\s+)?fotos|"
    r"no\s+(?:me\s+)?(?:llegaron|mandaron|enviaron)\s+(?:las\s+)?fotos|"
    r"sin\s+fotos|faltan\s+(?:las\s+)?fotos"
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
    text = (current_user_text or "").strip()
    return bool(
        _DETAIL_REQUEST_RE.search(text) or _MISSING_MEDIA_RE.search(text)
    )


def user_reports_missing_media(current_user_text: str) -> bool:
    return bool(_MISSING_MEDIA_RE.search((current_user_text or "").strip()))


def user_wants_specific_property_detail(current_user_text: str) -> bool:
    """Detalle de UNA propiedad (más info, me gusta la de X, fotos)."""
    return (
        user_requests_property_detail(current_user_text)
        or user_showed_property_interest(current_user_text)
        or user_reports_missing_media(current_user_text)
    )


def user_showed_property_interest(current_user_text: str) -> bool:
    return bool(_PROPERTY_INTEREST_RE.search((current_user_text or "").strip()))


def bot_promises_visual_material(outbound_message: str) -> bool:
    return bool(_BOT_VISUAL_PROMISE_RE.search((outbound_message or "").strip()))


def _message_has_characteristics_block(text: str) -> bool:
    return bool(re.search(r"\*Características:\*", text or "", re.I))


def should_deliver_property_detail_ficha(
    *,
    flow_path: str,
    property_ref: str,
    row: dict[str, Any] | None,
    outbound_message: str,
    current_user_text: str,
    history: list | None = None,
) -> bool:
    """Hay fila de catálogo y contexto de detalle / propiedad elegida."""
    path = (flow_path or "").strip().lower()
    if path in ("nuevo", "captacion") or row is None:
        return False
    if _LISTADO_TAG_RE.search(outbound_message or ""):
        return False
    if (property_ref or "").strip():
        if path in ("compra", "alquiler") and not user_search_profile_ready(
            history or [],
            current_user_text,
            flow_path,
        ):
            explicit = (
                user_requests_property_detail(current_user_text)
                or user_reports_missing_media(current_user_text)
                or user_showed_property_interest(current_user_text)
            )
            if not explicit:
                return False
        return True
    return should_enrich_property_detail(
        outbound_message=outbound_message,
        current_user_text=current_user_text,
        flow_path=flow_path,
        history=history,
    )


def should_enrich_property_detail(
    *,
    outbound_message: str,
    current_user_text: str,
    flow_path: str,
    history: list | None = None,
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

    profile_ready = user_search_profile_ready(
        history or [],
        current_user_text,
        flow_path,
    )
    explicit_detail = (
        user_requests_property_detail(current_user_text)
        or user_reports_missing_media(current_user_text)
        or user_showed_property_interest(current_user_text)
    )
    if path in ("compra", "alquiler") and not profile_ready and not explicit_detail:
        return False

    if user_requests_property_detail(current_user_text):
        return True
    if user_reports_missing_media(current_user_text):
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


def _rows_from_recent_listado(
    history: list | None,
    catalog_csv_path: str | None,
) -> list[dict[str, Any]]:
    """Filas del último [LISTADO:...] en el historial (opciones que vio el cliente)."""
    if not history or not catalog_csv_path:
        return []
    for turn in reversed(history):
        if turn.role != "assistant":
            continue
        match = _LISTADO_IDS_RE.search(turn.content or "")
        if not match:
            continue
        ids = [
            pid.strip()
            for pid in re.split(r"[,;\s]+", match.group(1))
            if pid.strip()
        ]
        rows = get_properties_by_ids(catalog_csv_path, ids, max_items=3)
        if rows:
            return rows
    return []


def resolve_detail_property_row(
    *,
    catalog_csv_path: str | None,
    current_user_text: str,
    outbound_message: str,
    history: list | None,
    property_ref: str,
    flow_path: str,
    catalog_sale_path: str | None,
    catalog_rent_path: str | None,
) -> dict[str, Any] | None:
    """Resuelve fila del catálogo para enviar ficha + media."""
    ref = property_ref_for_detail_enrich(
        current_user_text=current_user_text,
        outbound_message=outbound_message,
        history=history or [],
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        fallback_ref=property_ref,
        catalog_csv_path=catalog_csv_path,
    )
    if not ref and (property_ref or "").strip():
        ref = property_ref.strip()

    row: dict[str, Any] | None = None
    if ref:
        row = get_property_row_by_ref(catalog_csv_path, ref)

    if row is None:
        listado_rows = _rows_from_recent_listado(history, catalog_csv_path)
        for blob in (current_user_text, outbound_message):
            if not (blob or "").strip():
                continue
            row = find_property_row_for_user_text(
                catalog_csv_path,
                blob,
                rows_scope=listado_rows or None,
            )
            if row is not None:
                break

    if row is None and history:
        for turn in reversed(history or []):
            if turn.role != "user":
                continue
            row = find_property_row_for_user_text(
                catalog_csv_path, turn.content
            )
            if row is not None:
                break

    return row


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
    """Referencia desde mensaje del usuario (prioridad), historial o fallback."""
    ref_user = extract_property_ref(
        "",
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        history=[],
        current_user_text=current_user_text,
        user_only=True,
    )
    if ref_user.strip():
        return ref_user.strip()

    opt_ref = _property_ref_from_option_number(current_user_text, catalog_csv_path)
    if opt_ref:
        return opt_ref

    if (fallback_ref or "").strip():
        return fallback_ref.strip()

    if (outbound_message or "").strip() and (
        bot_promises_visual_material(outbound_message)
        or user_showed_property_interest(current_user_text)
    ):
        ref_bot = extract_property_ref(
            "",
            flow_path=flow_path,
            catalog_sale_path=catalog_sale_path,
            catalog_rent_path=catalog_rent_path,
            history=[],
            current_user_text=outbound_message,
            user_only=True,
        )
        if ref_bot.strip():
            return ref_bot.strip()

    opt_out = _property_ref_from_option_number(outbound_message, catalog_csv_path)
    if opt_out:
        return opt_out

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

    return ""


def strip_property_media_from_message(text: str) -> str:
    """Quita bloques de galería/video/características fuera de contexto de detalle."""
    if not (text or "").strip():
        return text

    text = replace_markdown_links_with_labels(text)
    text = re.sub(r"https?://\S+", "", text)
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
        if _LISTADO_TAG_RE.search(stripped):
            continue
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
        history=history,
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

    row = resolve_detail_property_row(
        catalog_csv_path=catalog_csv_path,
        current_user_text=current_user_text,
        outbound_message=body,
        history=history,
        property_ref=ref or property_ref,
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
    )
    if row is None:
        row = get_property_row_by_ref(catalog_csv_path, ref)
    if row is None:
        logger.warning("detail_media: ref=%r sin fila en catálogo", ref)
        return body

    cleaned = strip_property_media_from_message(body)
    logger.info(
        "detail_media: mensaje listo para envío estructurado id=%s",
        row.get("ID"),
    )
    return cleaned


async def _deliver_property_media_ctas(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    row: dict[str, Any],
    graph_version: str | None = None,
    include_preview_cta: bool = False,
) -> str:
    """Envía botones CTA (URL oculta). Retorna texto para historial."""
    buttons = collect_media_link_buttons(
        row, include_preview_cta=include_preview_cta
    )
    if not buttons:
        return ""

    intro = build_detail_media_intro(row)
    sent_any = False
    for index, btn in enumerate(buttons):
        if index == 0 and intro:
            body = intro
        elif len(buttons) == 1:
            body = "Tocá el botón para abrir 👇"
        else:
            body = f"Tocá *{btn.label}* 👇"
        try:
            await send_whatsapp_cta_url_message(
                access_token=access_token,
                phone_number_id=phone_number_id,
                to_wa_id=to_wa_id,
                body_text=body,
                button_label=btn.label,
                url=btn.url,
                graph_version=graph_version,
            )
            sent_any = True
        except Exception:
            logger.exception(
                "CTA fallo id=%s label=%s; se intentara fallback texto",
                row.get("ID"),
                btn.label,
            )

    if sent_any:
        return format_media_buttons_for_history(buttons)

    fallback = format_media_urls_text_fallback(row)
    if fallback:
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=fallback,
            graph_version=graph_version,
            preview_url=True,
        )
        return fallback
    return ""


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

    row = resolve_detail_property_row(
        catalog_csv_path=catalog_csv_path,
        current_user_text=current_user_text,
        outbound_message=body,
        history=history,
        property_ref=property_ref,
        flow_path=flow_path,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
    )

    if not should_deliver_property_detail_ficha(
        flow_path=flow_path,
        property_ref=property_ref,
        row=row,
        outbound_message=body,
        current_user_text=current_user_text,
        history=history,
    ):
        return None

    assert row is not None

    intro_part = _split_detail_intro(body)
    tail_part = extract_detail_tail(body)
    if not tail_part.strip():
        _, tail_part = _split_after_visual_intro(body)

    caption = build_detail_delivery_caption(
        row,
        intro=intro_part,
        tail=tail_part,
        catalog_csv_path=catalog_csv_path,
        branch=flow_path,
    )

    primary = primary_photo_url(row)
    gallery = gallery_photo_url(row)
    photo = detail_image_url(primary, gallery)
    can_send_image = bool(photo and is_public_https_image_url(photo))

    if can_send_image:
        await send_whatsapp_image_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            image_url=photo,
            caption=caption,
            graph_version=graph_version,
        )
    else:
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=caption,
            graph_version=graph_version,
            preview_url=False,
        )

    cta_history = await _deliver_property_media_ctas(
        access_token=access_token,
        phone_number_id=phone_number_id,
        to_wa_id=to_wa_id,
        row=row,
        graph_version=graph_version,
        include_preview_cta=not can_send_image,
    )

    consolidated = "\n\n".join(p for p in (caption, cta_history) if p.strip())
    logger.info(
        "detail_media: ficha id=%s imagen=%s botones=%s",
        row.get("ID"),
        can_send_image,
        bool(cta_history),
    )
    return consolidated


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
