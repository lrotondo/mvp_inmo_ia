from __future__ import annotations

import logging
import os
import re

import httpx

_URL_IN_TEXT = re.compile(r"https?://", re.I)
_HTTPS_IMAGE_URL = re.compile(r"^https://", re.I)

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
    u = (url or "").strip()
    return bool(u) and bool(_HTTPS_IMAGE_URL.match(u))


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
        preview_url = bool(_URL_IN_TEXT.search(body))
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {
            "preview_url": preview_url,
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


def _truncate_cta_display_text(label: str, *, max_len: int = 20) -> str:
    text = (label or "").strip() or "Abrir enlace"
    if len(text) <= max_len:
        return text
    return text[:max_len]


async def send_whatsapp_cta_url_message(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    body: str,
    button_label: str,
    url: str,
    footer: str | None = None,
    graph_version: str | None = None,
) -> None:
    """Botón CTA: el cliente ve solo el texto del botón, no la URL."""
    link = (url or "").strip()
    if not link.lower().startswith("https://"):
        raise ValueError(f"CTA url debe ser HTTPS: {link[:80]!r}")

    body_text = (body or "").strip() or "Tocá el botón para abrir:"
    interactive: dict = {
        "type": "cta_url",
        "body": {"text": body_text[:1024]},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": _truncate_cta_display_text(button_label),
                "url": link,
            },
        },
    }
    foot = (footer or "").strip()
    if foot:
        interactive["footer"] = {"text": foot[:60]}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": interactive,
    }
    await _post_whatsapp_payload(
        access_token=access_token,
        phone_number_id=phone_number_id,
        to_wa_id=to_wa_id,
        payload=payload,
        graph_version=graph_version,
        log_label=f"cta_url btn={button_label[:20]!r}",
    )
