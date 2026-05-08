from __future__ import annotations

import os

import httpx


def _graph_messages_url(phone_number_id: str, graph_version: str | None) -> str:
    version = (graph_version or os.environ.get("META_GRAPH_VERSION", "v22.0")).strip() or "v22.0"
    pid = phone_number_id.strip()
    if not pid:
        raise RuntimeError("phone_number_id vacio")
    return f"https://graph.facebook.com/{version}/{pid}/messages"


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

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message.strip() or "No pude generar una respuesta en este momento.",
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    url = _graph_messages_url(phone_number_id, graph_version)
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
