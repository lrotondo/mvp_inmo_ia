from __future__ import annotations

import os

import httpx


def _graph_api_url() -> str:
    version = os.environ.get("META_GRAPH_VERSION", "v22.0").strip() or "v22.0"
    phone_number_id = os.environ.get("META_PHONE_NUMBER_ID", "").strip()
    if not phone_number_id:
        raise RuntimeError("META_PHONE_NUMBER_ID no configurada")
    return f"https://graph.facebook.com/{version}/{phone_number_id}/messages"


def _graph_access_token() -> str:
    token = os.environ.get("META_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN no configurada")
    return token


async def send_whatsapp_text_message(to_wa_id: str, message: str) -> None:
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
        "Authorization": f"Bearer {_graph_access_token()}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(_graph_api_url(), headers=headers, json=payload)
        response.raise_for_status()
