from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MetaGraphError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def graph_version() -> str:
    return (os.environ.get("META_GRAPH_VERSION", "v22.0") or "v22.0").strip()


def meta_app_id() -> str:
    return os.environ.get("META_APP_ID", "").strip()


def meta_app_secret() -> str:
    from app.meta_auth import _normalize_meta_app_secret

    return _normalize_meta_app_secret(os.environ.get("META_APP_SECRET", ""))


def _graph_base() -> str:
    return f"https://graph.facebook.com/{graph_version()}"


async def exchange_code_for_business_token(code: str) -> str:
    app_id = meta_app_id()
    secret = meta_app_secret()
    if not app_id or not secret:
        raise MetaGraphError("META_APP_ID o META_APP_SECRET no configurados")
    params = {
        "client_id": app_id,
        "client_secret": secret,
        "code": code.strip(),
    }
    url = f"{_graph_base()}/oauth/access_token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)
    if resp.status_code >= 400:
        logger.warning("oauth/access_token failed status=%s body=%s", resp.status_code, resp.text[:500])
        raise MetaGraphError(
            "No se pudo intercambiar el código de Embedded Signup",
            status_code=resp.status_code,
            payload=resp.text,
        )
    data = resp.json()
    token = str(data.get("access_token") or "").strip()
    if not token:
        # Meta a veces devuelve el token como texto plano
        token = resp.text.strip()
    if not token:
        raise MetaGraphError("Respuesta sin access_token", payload=data)
    return token


async def subscribe_waba_webhooks(waba_id: str, business_token: str) -> None:
    url = f"{_graph_base()}/{waba_id.strip()}/subscribed_apps"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {business_token.strip()}"},
        )
    if resp.status_code >= 400:
        raise MetaGraphError(
            "No se pudo suscribir webhooks al WABA",
            status_code=resp.status_code,
            payload=resp.text,
        )
    body = resp.json()
    if not body.get("success"):
        raise MetaGraphError("subscribed_apps sin success", payload=body)


async def register_phone_number(
    phone_number_id: str,
    business_token: str,
    pin: str,
) -> None:
    url = f"{_graph_base()}/{phone_number_id.strip()}/register"
    payload = {
        "messaging_product": "whatsapp",
        "pin": pin.strip(),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {business_token.strip()}"},
            json=payload,
        )
    if resp.status_code >= 400:
        # Número ya registrado es común en reconexiones
        text = resp.text.lower()
        if "already" in text or "registered" in text:
            logger.info("register: número ya registrado phone_number_id=%s", phone_number_id)
            return
        raise MetaGraphError(
            "No se pudo registrar el número",
            status_code=resp.status_code,
            payload=resp.text,
        )
    body = resp.json()
    if not body.get("success"):
        raise MetaGraphError("register sin success", payload=body)


async def get_phone_number_display(phone_number_id: str, business_token: str) -> str | None:
    url = f"{_graph_base()}/{phone_number_id.strip()}"
    params = {"fields": "display_phone_number,verified_name"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {business_token.strip()}"},
        )
    if resp.status_code >= 400:
        return None
    data = resp.json()
    return str(data.get("display_phone_number") or "").strip() or None
