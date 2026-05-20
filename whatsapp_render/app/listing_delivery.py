from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from app.catalog import (
    get_properties_by_ids,
    primary_photo_url,
)
from app.friendly_links import deliver_text_with_friendly_links
from app.meta_client import (
    is_public_https_image_url,
    send_whatsapp_image_message,
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


def tour_360_url(row: dict[str, Any]) -> str:
    return str(row.get("Tour_360") or row.get("Tour_360_URL") or "").strip()


def build_listing_caption(row: dict[str, Any], index: int) -> str:
    """Caption para mensaje imagen: título + datos + tour 360 opcional."""
    direccion = str(row.get("Direccion", "")).strip()
    barrio = str(row.get("Barrio", "")).strip()
    ubicacion = direccion
    if barrio:
        ubicacion = f"{direccion}, {barrio}" if direccion else barrio

    precio = str(row.get("Precio", "")).strip()
    ambientes = str(row.get("Ambientes", "")).strip()
    caracteristicas = str(row.get("Caracteristicas", "")).strip()

    tipo = ""
    if caracteristicas:
        first = caracteristicas.split("-")[0].strip()
        if first:
            tipo = first

    title = f"*Opción {index} — {ubicacion}*" if ubicacion else f"*Opción {index}*"

    detail_parts: list[str] = []
    if precio:
        detail_parts.append(f"Precio: ${precio}" if not precio.startswith("$") else f"Precio: {precio}")
    if ambientes:
        detail_parts.append(f"{ambientes} ambientes")
    if tipo:
        detail_parts.append(tipo)

    lines = [title]
    if detail_parts:
        lines.append(" | ".join(detail_parts))

    tour = tour_360_url(row)
    if tour:
        lines.append(f"🔄 Tour 360°: {tour}")

    return "\n".join(lines)


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
) -> str:
    """
    Envía la respuesta al cliente. Listados con [LISTADO:ids] → intro + imágenes + cierre.
    Retorna texto consolidado para historial / detección de handoff.
    """
    body = (message or "").strip() or "No pude generar una respuesta en este momento."

    if not listing_image_delivery_enabled():
        return await deliver_text_with_friendly_links(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=body,
            graph_version=graph_version,
        )

    parsed = parse_listado_tag(body)
    if parsed is None:
        return await deliver_text_with_friendly_links(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=body,
            graph_version=graph_version,
        )

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
        return await deliver_text_with_friendly_links(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=fallback,
            graph_version=graph_version,
        )

    sendable: list[tuple[dict[str, Any], str, str | None]] = []
    for idx, row in enumerate(rows, start=1):
        caption = build_listing_caption(row, idx)
        photo = primary_photo_url(row)
        image_url = photo if is_public_https_image_url(photo) else None
        sendable.append((row, caption, image_url))

    if not any(url for _, _, url in sendable):
        logger.info("listado_sin_imagenes_https ids=%s; fallback texto", parsed.property_ids)
        fallback = parsed.text_without_tag or body
        return await deliver_text_with_friendly_links(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=fallback,
            graph_version=graph_version,
        )

    if parsed.intro.strip():
        await deliver_text_with_friendly_links(
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
                sent = await deliver_text_with_friendly_links(
                    access_token=access_token,
                    phone_number_id=phone_number_id,
                    to_wa_id=to_wa_id,
                    message=fallback_item,
                    graph_version=graph_version,
                )
                history_items.append(sent)
        else:
            fallback_item = build_listing_fallback_text(row, idx)
            sent = await deliver_text_with_friendly_links(
                access_token=access_token,
                phone_number_id=phone_number_id,
                to_wa_id=to_wa_id,
                message=fallback_item,
                graph_version=graph_version,
            )
            history_items.append(sent)

    if parsed.closing.strip():
        await deliver_text_with_friendly_links(
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
