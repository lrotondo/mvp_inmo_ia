from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass

import httpx

from app.media_urls import is_likely_direct_image_url

_URL_IN_TEXT = re.compile(r"https?://", re.I)

logger = logging.getLogger(__name__)

_META_RETRY_ATTEMPTS = 4
_META_RETRY_BASE_SECONDS = 1.0
_TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
_TRANSIENT_ERROR_CODES = frozenset({1, 2, 4, 17, 32, 613})


@dataclass(frozen=True)
class MetaSendError(Exception):
    """Fallo al enviar mensaje por Graph API (tras reintentos si aplica)."""

    message: str
    status_code: int | None = None
    error_code: int | None = None
    is_transient: bool = False
    response_body: str = ""

    def __str__(self) -> str:
        return self.message


def _parse_meta_error_payload(response: httpx.Response) -> tuple[bool, int | None, str]:
    try:
        data = response.json()
    except Exception:
        return False, None, ""
    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return False, None, ""
    code_raw = err.get("code")
    try:
        code = int(code_raw) if code_raw is not None else None
    except (TypeError, ValueError):
        code = None
    transient = bool(err.get("is_transient"))
    if code in _TRANSIENT_ERROR_CODES:
        transient = True
    msg = str(err.get("message") or "")
    return transient, code, msg


def _should_retry_meta_send(
    response: httpx.Response,
    *,
    attempt: int,
    max_attempts: int,
) -> bool:
    if attempt >= max_attempts:
        return False
    if response.status_code in _TRANSIENT_HTTP_STATUSES:
        return True
    transient, _, _ = _parse_meta_error_payload(response)
    return transient


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

    last_response: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(1, _META_RETRY_ATTEMPTS + 1):
            response = await client.post(url, headers=headers, json=payload)
            last_response = response
            logger.info(
                "Meta response %s: status=%s attempt=%s/%s content_length=%s",
                log_label,
                response.status_code,
                attempt,
                _META_RETRY_ATTEMPTS,
                response.headers.get("content-length"),
            )
            if not response.is_error:
                logger.info("Meta send OK %s: body=%s", log_label, response.text[:500])
                return

            transient, err_code, err_msg = _parse_meta_error_payload(response)
            logger.error(
                "Meta send FAILED %s: status=%s transient=%s code=%s attempt=%s body=%s",
                log_label,
                response.status_code,
                transient,
                err_code,
                attempt,
                response.text[:2000],
            )
            if _should_retry_meta_send(
                response, attempt=attempt, max_attempts=_META_RETRY_ATTEMPTS
            ):
                delay = _META_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                logger.info(
                    "Meta send retry %s en %.1fs (transient=%s)",
                    log_label,
                    delay,
                    transient,
                )
                await asyncio.sleep(delay)
                continue

            raise MetaSendError(
                message=err_msg or f"Meta API error HTTP {response.status_code}",
                status_code=response.status_code,
                error_code=err_code,
                is_transient=transient,
                response_body=response.text[:2000],
            )

    if last_response is not None:
        transient, err_code, err_msg = _parse_meta_error_payload(last_response)
        raise MetaSendError(
            message=err_msg or "Meta API error",
            status_code=last_response.status_code,
            error_code=err_code,
            is_transient=transient,
            response_body=last_response.text[:2000],
        )
    raise MetaSendError(message="Meta API sin respuesta")


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


async def send_whatsapp_cta_url_message(
    *,
    access_token: str,
    phone_number_id: str,
    to_wa_id: str,
    body_text: str,
    button_label: str,
    url: str,
    graph_version: str | None = None,
) -> None:
    """
    Botón con URL (WhatsApp no soporta markdown [texto](url) en el cuerpo).
    display_text máx. 20 caracteres; la URL no se muestra en el mensaje.
    """
    body = (body_text or "👇").strip()[:1024]
    label = (button_label or "Abrir enlace").strip()[:20]
    link = (url or "").strip()
    if not link.lower().startswith("https://"):
        raise ValueError(f"CTA url invalida: {link[:80]!r}")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": body},
            "action": {
                "name": "cta_url",
                "parameters": {
                    "display_text": label,
                    "url": link,
                },
            },
        },
    }
    await _post_whatsapp_payload(
        access_token=access_token,
        phone_number_id=phone_number_id,
        to_wa_id=to_wa_id,
        payload=payload,
        graph_version=graph_version,
        log_label=f"cta_url label={label!r}",
    )
