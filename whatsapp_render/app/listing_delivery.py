from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from app.catalog import get_properties_by_ids, primary_photo_url
from app.detail_media import (
    try_deliver_single_property_visual,
    user_wants_specific_property_detail,
)
from app.lead_context import user_search_profile_ready
from app.property_ficha import build_property_ficha
from app.meta_client import (
    is_public_https_image_url,
    send_whatsapp_image_message,
    send_whatsapp_text_message,
)

logger = logging.getLogger(__name__)

_LISTADO_TAG_RE = re.compile(r"\[LISTADO:([^\]]+)\]", re.I)
_CATALOG_ESSAY_LINE_RE = re.compile(
    r"\|\s*Precio:|\*Características|dormitorios\s*\||"
    r"Living\s+comedor|toilette|baño\s+en\s+suite|"
    r"Departamento\s+a\s+estrenar|tercer\s+piso\s+por\s+ascensor",
    re.I,
)
_INVENTED_LISTING_LINE_RE = re.compile(
    r"(?:"
    r"USD\s*[\d.,]+|US\$[\d.,]+|"
    r"\$\s*[\d.,]+\s*/?\s*mes|"
    r"[\d.,]+\s*/?\s*mes|"
    r"\*?\s*Zona\s+(?:Norte|Sur|Oeste|Este)\*?|"
    r"(?:Casa|Depto|Departamento)\s+en\s+\*?|"
    r"\d+\s*dormitorios?.*(?:USD|US\$|\$|/mes)|"
    r"Precio\s+USD\s*[\d.,]+|"
    r"Precio\s+mensual\s+ARS"
    r")",
    re.I,
)
_NUMBERED_PROPERTY_LINE_RE = re.compile(
    r"^\s*\d+[\.\)]\s*\*?(?:Casa|Depto|Departamento|Duplex)\b",
    re.I,
)
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


def _strip_catalog_essay_lines(text: str) -> str:
    kept: list[str] = []
    for line in (text or "").splitlines():
        if _CATALOG_ESSAY_LINE_RE.search(line):
            continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _line_looks_invented_property(stripped: str) -> bool:
    if not stripped:
        return False
    if _NUMBERED_PROPERTY_LINE_RE.match(stripped):
        return True
    if _INVENTED_LISTING_LINE_RE.search(stripped) and re.search(r"\d", stripped):
        return True
    if re.search(
        r"\b(?:casa|depto|departamento)\s+en\s+[^|\n]{3,}",
        stripped,
        re.I,
    ) and re.search(r"[\d$]", stripped):
        return True
    return False


def strip_invented_listings(message: str) -> str:
    """Quita viñetas en prosa con precios/zonas inventadas (sin [LISTADO:])."""
    body = (message or "").strip()
    if not body:
        return body
    if _LISTADO_TAG_RE.search(body):
        return _strip_catalog_essay_lines(body)

    kept: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        if _line_looks_invented_property(stripped):
            continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _listado_ids_valid(
    property_ids: list[str],
    catalog_csv_path: str | None,
) -> bool:
    if not property_ids:
        return False
    rows = get_properties_by_ids(
        catalog_csv_path,
        property_ids,
        max_items=_MAX_LISTING_ITEMS,
    )
    found = {str(r.get("ID", "")).strip() for r in rows}
    return all(pid in found for pid in property_ids)


def ensure_listado_from_candidates(
    message: str,
    candidate_ids: list[str],
    catalog_csv_path: str | None,
) -> str:
    """
    Garantiza [LISTADO:ids] del backend cuando el LLM listó en prosa o omitió el tag.
    """
    ids = [pid.strip() for pid in candidate_ids if pid.strip()][:_MAX_LISTING_ITEMS]
    if not ids:
        cleaned = strip_invented_listings(message)
        if cleaned and not _line_looks_invented_property(cleaned):
            return cleaned
        return (
            "Por ahora no tengo opciones en catálogo que coincidan exactamente con lo que "
            "pediste. ¿Querés ampliar zona, tipo o presupuesto para buscar de nuevo?"
        )

    body = strip_invented_listings(message)
    parsed = parse_listado_tag(body)
    if parsed and _listado_ids_valid(parsed.property_ids, catalog_csv_path):
        return body

    tag_line = f"[LISTADO:{','.join(ids)}]"
    if parsed:
        intro = _strip_catalog_essay_lines(parsed.intro)
        closing = _strip_catalog_essay_lines(parsed.closing)
        parts = [p for p in (intro, tag_line, closing) if p.strip()]
        return "\n\n".join(parts)

    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    intro_lines: list[str] = []
    closing_lines: list[str] = []
    for line in lines:
        if _INVENTED_LISTING_LINE_RE.search(line):
            continue
        if not intro_lines:
            intro_lines.append(line)
        else:
            closing_lines.append(line)

    intro = "\n".join(intro_lines[:4]).strip()
    closing = "\n".join(closing_lines[-2:]).strip()
    if not closing or closing.lower() == intro.lower():
        closing = "¿Alguna de estas opciones te llama la atención para pasarte más detalles?"

    parts = [intro, tag_line, closing]
    result = "\n\n".join(p for p in parts if p.strip())
    logger.info("listado_inyectado_backend ids=%s", ids)
    return result


def suppress_premature_catalog_outbound(
    message: str,
    *,
    history: list | None,
    current_user_text: str,
    flow_path: str,
) -> str:
    """
    Quita listados y fichas si el cliente aún no dio zona + dormitorios.
    El LLM a veces ignora el prompt; el backend no envía fotos ni IDs.
    """
    if user_search_profile_ready(
        history or [],
        current_user_text,
        flow_path,
    ):
        return strip_invented_listings(message)

    body = (message or "").strip()
    if not body:
        return body

    parsed = parse_listado_tag(body)
    if parsed is not None:
        parts = [p for p in (parsed.intro, parsed.closing) if p.strip()]
        cleaned = _strip_catalog_essay_lines("\n\n".join(parts).strip())
        logger.info(
            "listado_suprimido flow=%s (perfil sin zona+dormitorios)",
            flow_path,
        )
        return cleaned or body

    if _LISTADO_TAG_RE.search(body):
        body = _LISTADO_TAG_RE.sub("", body).strip()

    cleaned = strip_invented_listings(_strip_catalog_essay_lines(body))
    return cleaned or body


def strip_listado_tags(text: str) -> str:
    """Quita `[LISTADO:ids]` del texto visible al cliente."""
    cleaned = _LISTADO_TAG_RE.sub("", text or "")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


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


def build_listing_caption(
    row: dict[str, Any],
    index: int,
    *,
    flow_path: str = "compra",
) -> str:
    """Caption para mensaje imagen: encabezado + características (+ tour si aplica)."""
    return build_property_ficha(
        row,
        include_media_links=False,
        option_index=index,
        branch=flow_path,
    )


def build_listing_fallback_text(
    row: dict[str, Any],
    index: int,
    *,
    flow_path: str = "compra",
) -> str:
    """Texto cuando no hay imagen enviable (sin URLs crudas en el cuerpo)."""
    return build_listing_caption(row, index, flow_path=flow_path)


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
    capture_data: dict[str, Any] | None = None,
) -> str:
    """
    Envía la respuesta al cliente. Listados con [LISTADO:ids] → intro + imágenes + cierre.
    Retorna texto consolidado para historial / detección de handoff.
    """
    body = (message or "").strip() or "No pude generar una respuesta en este momento."
    body = suppress_premature_catalog_outbound(
        body,
        history=history,
        current_user_text=current_user_text,
        flow_path=flow_path,
    )

    parsed_listado = parse_listado_tag(body)
    detail_intent = user_wants_specific_property_detail(current_user_text)

    # Detalle de una propiedad: prioridad sobre [LISTADO] (evita "Opción 1" y tag visible).
    if detail_intent:
        detail_body = strip_listado_tags(body)
        visual_sent = await try_deliver_single_property_visual(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=detail_body,
            catalog_csv_path=catalog_csv_path,
            current_user_text=current_user_text,
            flow_path=flow_path,
            history=history,
            catalog_sale_path=catalog_sale_path,
            catalog_rent_path=catalog_rent_path,
            property_ref=property_ref,
            capture_data=capture_data,
            graph_version=graph_version,
        )
        if visual_sent is not None:
            return strip_listado_tags(visual_sent)

    # Listado multi-opción: no usar envío de detalle (1 foto + tag en caption).
    if parsed_listado is None:
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
            capture_data=capture_data,
            graph_version=graph_version,
        )
        if visual_sent is not None:
            return strip_listado_tags(visual_sent)

    if not listing_image_delivery_enabled():
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=body,
            graph_version=graph_version,
        )
        return body

    parsed = parsed_listado
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
        fallback = strip_listado_tags(parsed.text_without_tag or body)
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
        caption = build_listing_caption(row, idx, flow_path=flow_path)
        photo = primary_photo_url(row)
        image_url = photo if is_public_https_image_url(photo) else None
        sendable.append((row, caption, image_url))

    if not any(url for _, _, url in sendable):
        logger.info("listado_sin_imagenes_https ids=%s; fallback texto", parsed.property_ids)
        fallback = strip_listado_tags(parsed.text_without_tag or body)
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=fallback,
            graph_version=graph_version,
        )
        return fallback

    intro_text = _strip_catalog_essay_lines(strip_listado_tags(parsed.intro))
    closing_text = _strip_catalog_essay_lines(strip_listado_tags(parsed.closing))

    if intro_text:
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=intro_text,
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

    if closing_text:
        await send_whatsapp_text_message(
            access_token=access_token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            message=closing_text,
            graph_version=graph_version,
        )

    consolidated = consolidate_history_text(
        intro_text,
        history_items,
        closing_text,
    )
    if parsed.property_ids:
        tag = f"[LISTADO:{','.join(parsed.property_ids)}]"
        consolidated = f"{consolidated}\n\n{tag}".strip()
    logger.info(
        "listado_multi_imagen enviado items=%s ids=%s",
        len(history_items),
        parsed.property_ids,
    )
    return consolidated or parsed.text_without_tag or body
