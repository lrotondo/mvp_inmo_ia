from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from app.catalog import get_properties_by_ids, primary_photo_url
from app.detail_media import try_deliver_single_property_visual
from app.property_ficha import build_property_ficha
from app.meta_client import (
    is_public_https_image_url,
    send_whatsapp_image_message,
    send_whatsapp_text_message,
)

logger = logging.getLogger(__name__)

_LISTADO_TAG_RE = re.compile(r"\[LISTADO:([^\]]+)\]", re.I)
_MAX_LISTING_ITEMS = 3


@dataclass(frozen=True)
class ParsedListado:
    intro: str
    property_ids: list[str]
    closing: str
    text_without_tag: str


def listing_image_delivery_enabled() -> bool:
    raw = os.environ.get("LISTING_IMAGE_DELIVERY", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def parse_listado_tag(text: str) -> ParsedListado | None:
    """Extrae intro, IDs y cierre alrededor de [LISTADO:id1,id2,...]."""
    body = (text or "").strip()
    match = _LISTADO_TAG_RE.search(body)
    if not match:
        return None

    ids_raw = match.group(1)
    property_ids = [
        pid.strip()
        for pid in re.split(r"[,;\s]+", ids_raw)
        if pid.strip()
    ][: _MAX_LISTING_ITEMS]

    before = body[: match.start()].strip()
    after = body[match.end() :].strip()
    text_without_tag = re.sub(r"\n{3,}", "\n\n", f"{before}\n\n{after}".strip()).strip()

    return ParsedListado(
        intro=before,
        property_ids=property_ids,
        closing=after,
        text_without_tag=text_without_tag,
    )


def build_listing_caption(row: dict[str, Any], index: int) -> str:
    """Caption para mensaje imagen: encabezado + características (+ tour si aplica)."""
    return build_property_ficha(
        row,
        include_media_links=False,
        option_index=index,
    )


def build_listing_fallback_text(row: dict[str, Any], index: int) -> str:
    """Texto cuando no hay imagen enviable."""
    caption = build_listing_caption(row, index)
    photo = primary_photo_url(row)
    if photo:
        return f"{caption}\n📸 [Ver fotos]({photo})"
    return caption


def consolidate_history_text(
    intro: str,
    item_texts: list[str],
    closing: str,
) -> str:
    parts: list[str] = []
    if intro.strip():
        parts.append(intro.strip())
    parts.extend(t.strip() for t in item_texts if t.strip())
    if closing.strip():
        parts.append(closing.strip())
    return "\n\n".join(parts)


async def deliver_bot_response(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    message: str,
    catalog_csv_path: str | None,
    graph_version: str | None = None,
    current_user_text: str = "",
    flow_path: str = "compra",
    history: list | None = None,
    catalog_sale_path: str | None = None,
    catalog_rent_path: str | None = None,
    property_ref: str = "",
) -> str:
    """
    Envía la respuesta al cliente. Listados con [LISTADO:ids] → intro + imágenes + cierre.
    Retorna texto consolidado para historial / detección de handoff.
    """
    body = (message or "").strip() or "No pude generar una respuesta en este momento."

    visual_sent = await try_deliver_single_property_visual(
        access_token=access_token,
        phone_number_id=phone_number_id,
        to_wa_id=to_wa_id,
        message=body,
        catalog_csv_path=catalog_csv_path,
        current_user_text=current_user_text,
        flow_path=flow_path,
        history=history,
        catalog_sale_path=catalog_sale_path,
        catalog_rent_path=catalog_rent_path,
        property_ref=property_ref,
        graph_version=graph_version,
    )
    if visual_sent is not None:
        return visual_sent

    if not listing_image_delivery_enabled():
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=body,
            graph_version=graph_version,
        )
        return body

    parsed = parse_listado_tag(body)
    if parsed is None:
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=body,
            graph_version=graph_version,
        )
        return body

    rows = get_properties_by_ids(
        catalog_csv_path,
        parsed.property_ids,
        max_items=_MAX_LISTING_ITEMS,
    )
    if not rows:
        logger.info(
            "listado_sin_filas ids=%s path=%r; fallback texto",
            parsed.property_ids,
            catalog_csv_path,
        )
        fallback = parsed.text_without_tag or body
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=fallback,
            graph_version=graph_version,
        )
        return fallback

    sendable: list[tuple[dict[str, Any], str, str | None]] = []
    for idx, row in enumerate(rows, start=1):
        caption = build_listing_caption(row, idx)
        photo = primary_photo_url(row)
        image_url = photo if is_public_https_image_url(photo) else None
        sendable.append((row, caption, image_url))

    if not any(url for _, _, url in sendable):
        logger.info("listado_sin_imagenes_https ids=%s; fallback texto", parsed.property_ids)
        fallback = parsed.text_without_tag or body
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=fallback,
            graph_version=graph_version,
        )
        return fallback

    if parsed.intro.strip():
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=parsed.intro.strip(),
            graph_version=graph_version,
        )

    history_items: list[str] = []
    for idx, (row, caption, image_url) in enumerate(sendable, start=1):
        if image_url:
            try:
                await send_whatsapp_image_message(
                    access_token=access_token,
                    phone_number_id=phone_number_id,
                    to_wa_id=to_wa_id,
                    image_url=image_url,
                    caption=caption,
                    graph_version=graph_version,
                )
                history_items.append(caption)
            except Exception:
                logger.exception(
                    "listado imagen fallo id=%s url=%s",
                    row.get("ID"),
                    image_url[:80],
                )
                fallback_item = build_listing_fallback_text(row, idx)
                await send_whatsapp_text_message(
                    access_token=access_token,
                    phone_number_id=phone_number_id,
                    to_wa_id=to_wa_id,
                    message=fallback_item,
                    graph_version=graph_version,
                )
                history_items.append(fallback_item)
        else:
            fallback_item = build_listing_fallback_text(row, idx)
            await send_whatsapp_text_message(
                access_token=access_token,
                phone_number_id=phone_number_id,
                to_wa_id=to_wa_id,
                message=fallback_item,
                graph_version=graph_version,
            )
            history_items.append(fallback_item)

    if parsed.closing.strip():
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=parsed.closing.strip(),
            graph_version=graph_version,
        )

    consolidated = consolidate_history_text(
        parsed.intro,
        history_items,
        parsed.closing,
    )
    logger.info(
        "listado_multi_imagen enviado items=%s ids=%s",
        len(history_items),
        parsed.property_ids,
    )
    return consolidated or parsed.text_without_tag or body
