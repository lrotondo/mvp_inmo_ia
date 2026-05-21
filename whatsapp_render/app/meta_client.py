from __future__ import annotations

import logging
import os
import re

import httpx

from app.media_urls import is_likely_direct_image_url

_URL_IN_TEXT = re.compile(r"https?://", re.I)

logger = logging.getLogger(__name__)


def _graph_messages_url(phone_number_id: str, graph_version: str | None) -> str:
    version = (graph_version or os.environ.get("META_GRAPH_VERSION", "v22.0")).strip() or "v22.0"
    pid = phone_number_id.strip()
    if not pid:
        raise RuntimeError("phone_number_id vacio")
    return f"https://graph.facebook.com/{version}/{pid}/messages"


def _token_debug(token: str) -> str:
    t = token.strip()
    if not t:
        return "empty"
    suffix = t[-4:] if len(t) >= 4 else "****"
    return f"len={len(t)} suffix=…{suffix}"


def is_public_https_image_url(url: str) -> bool:
    """Alias: imagen directa HTTPS (excluye Instagram/perfiles)."""
    return is_likely_direct_image_url(url)


async def _post_whatsapp_payload(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    payload: dict,
    graph_version: str | None,
    log_label: str,
) -> None:
    token = access_token.strip()
    if not token:
        raise RuntimeError("access_token vacio")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = _graph_messages_url(phone_number_id, graph_version)
    logger.info(
        "Meta send %s: url=%s pnid=%s to=%s token=%s",
        log_label,
        url,
        phone_number_id.strip(),
        to_wa_id,
        _token_debug(token),
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    logger.info(
        "Meta response %s: status=%s content_length=%s",
        log_label,
        response.status_code,
        response.headers.get("content-length"),
    )

    if response.is_error:
        logger.error(
            "Meta send FAILED %s: status=%s body=%s",
            log_label,
            response.status_code,
            response.text[:2000],
        )
        response.raise_for_status()

    logger.info("Meta send OK %s: body=%s", log_label, response.text[:500])


async def send_whatsapp_text_message(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    message: str,
    graph_version: str | None = None,
    preview_url: bool | None = None,
) -> None:
    body = message.strip() or "No pude generar una respuesta en este momento."
    if preview_url is None:
        enable_preview = bool(_URL_IN_TEXT.search(body))
    else:
        enable_preview = preview_url
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {
            "preview_url": enable_preview,
            "body": body,
        },
    }
    await _post_whatsapp_payload(
        access_token=access_token,
        phone_number_id=phone_number_id,
        to_wa_id=to_wa_id,
        payload=payload,
        graph_version=graph_version,
        log_label=f"text body_len={len(body)}",
    )


async def send_whatsapp_image_message(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    image_url: str,
    caption: str = "",
    graph_version: str | None = None,
) -> None:
    link = (image_url or "").strip()
    if not is_public_https_image_url(link):
        raise ValueError(f"image_url invalida o no HTTPS: {link[:80]!r}")

    image_payload: dict[str, str] = {"link": link}
    cap = (caption or "").strip()
    if cap:
        image_payload["caption"] = cap[:1024]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "image",
        "image": image_payload,
    }
    await _post_whatsapp_payload(
        access_token=access_token,
        phone_number_id=phone_number_id,
        to_wa_id=to_wa_id,
        payload=payload,
        graph_version=graph_version,
        log_label=f"image cap_len={len(cap)}",
    )
