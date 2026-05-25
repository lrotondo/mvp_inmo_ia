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


def system_user_access_token() -> str:
    """System User con whatsapp_business_management (fetch phone_numbers en webhook)."""
    return os.environ.get("META_SYSTEM_USER_ACCESS_TOKEN", "").strip()


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


_PHONE_LIST_FIELDS = (
    "id,display_phone_number,verified_name,"
    "code_verification_status,status,account_mode"
)


async def list_waba_phone_numbers(waba_id: str, access_token: str) -> list[dict[str, Any]]:
    """GET /{waba_id}/phone_numbers — números del WABA del cliente."""
    token = (access_token or "").strip()
    if not token:
        raise MetaGraphError("Token de acceso vacío para listar phone_numbers")
    url = f"{_graph_base()}/{waba_id.strip()}/phone_numbers"
    params = {"fields": _PHONE_LIST_FIELDS}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code >= 400:
        raise MetaGraphError(
            "No se pudo listar phone_numbers del WABA",
            status_code=resp.status_code,
            payload=resp.text,
        )
    data = resp.json()
    raw = data.get("data")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _phone_row_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or "").strip()


def _is_sandbox_phone(row: dict[str, Any]) -> bool:
    mode = str(row.get("account_mode") or "").strip().upper()
    return mode == "SANDBOX"


def pick_default_phone_number_id(rows: list[dict[str, Any]]) -> str | None:
    """Elige un phone_number_id cuando Meta no lo envía en el webhook."""
    candidates = [r for r in rows if _phone_row_id(r)]
    if not candidates:
        return None
    non_sandbox = [r for r in candidates if not _is_sandbox_phone(r)]
    pool = non_sandbox or candidates
    verified = [
        r
        for r in pool
        if str(r.get("code_verification_status") or "").strip().upper() == "VERIFIED"
    ]
    if len(verified) == 1:
        return _phone_row_id(verified[0])
    if len(verified) > 1:
        logger.warning(
            "pick_default_phone_number_id: varios números VERIFIED, usando el primero"
        )
        return _phone_row_id(verified[0])
    if len(pool) == 1:
        return _phone_row_id(pool[0])
    logger.warning(
        "pick_default_phone_number_id: varios números en WABA (%s), usando el primero",
        len(pool),
    )
    return _phone_row_id(pool[0])


async def resolve_phone_number_id_for_waba(
    waba_id: str,
    access_token: str,
) -> str | None:
    rows = await list_waba_phone_numbers(waba_id, access_token)
    return pick_default_phone_number_id(rows)
