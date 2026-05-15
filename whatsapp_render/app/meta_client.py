from __future__ import annotations

import logging
import os
import re

import httpx

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


async def send_whatsapp_text_message(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    message: str,
    graph_version: str | None = None,
) -> None:
    token = access_token.strip()
    if not token:
        raise RuntimeError("access_token vacio")

    body = message.strip() or "No pude generar una respuesta en este momento."
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {
            "preview_url": bool(_URL_IN_TEXT.search(body)),
            "body": body,
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    url = _graph_messages_url(phone_number_id, graph_version)
    logger.info(
        "Meta send: url=%s pnid=%s to=%s body_len=%s token=%s",
        url,
        phone_number_id.strip(),
        to_wa_id,
        len(body),
        _token_debug(token),
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    logger.info(
        "Meta response: status=%s content_length=%s",
        response.status_code,
        response.headers.get("content-length"),
    )

    if response.is_error:
        logger.error(
            "Meta send FAILED: status=%s body=%s",
            response.status_code,
            response.text[:2000],
        )
        response.raise_for_status()

    logger.info("Meta send OK: body=%s", response.text[:500])
