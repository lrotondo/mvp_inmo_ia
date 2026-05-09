from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.catalog import (
    filter_properties,
    format_catalog,
    load_properties_for_catalog_path,
)
from app.db import dispose_engine, get_engine, init_db
from app.groq_client import chat_completion
from app.meta_auth import (
    validate_meta_signature,
    validate_meta_verify_token,
)
from app.meta_client import send_whatsapp_text_message
from app.tenant_service import (
    TenantContext,
    fetch_tenant_context,
)

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

    root = logging.getLogger()

    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format=fmt,
        )

    for name in (
        "app",
        "app.main",
        "app.db",
        "app.tenant_service",
        "app.meta_client",
    ):
        logging.getLogger(name).setLevel(logging.INFO)


DEFAULT_SYSTEM_PROMPT = (
    "Sos un asesor inmobiliario experto en Tandil y zona. "
    "Responde cordial y breve por WhatsApp. "
    "Solo usa datos del catalogo. "
    "Si no alcanza, decilo y no inventes."
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_logging()

    logger.info("========== APP START ==========")

    init_db()

    logger.info(
        "Arranque: db_engine=%s",
        "on" if get_engine() is not None else "off",
    )

    yield

    logger.info("========== APP STOP ==========")

    dispose_engine()


app = FastAPI(
    title="WhatsApp Inmobiliaria MVP",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict[str, str]:
    logger.info("GET /")
    return {
        "service": "whatsapp_render",
        "health": "/health",
        "webhook": "/meta/whatsapp",
    }


@app.get("/health")
def health() -> dict[str, str]:
    logger.info("GET /health")

    return {
        "status": "ok",
        "db": "on" if get_engine() is not None else "off",
    }


def _legacy_tenant_context() -> TenantContext | None:
    token = os.environ.get("META_ACCESS_TOKEN", "").strip()
    pid = os.environ.get("META_PHONE_NUMBER_ID", "").strip()

    if not token or not pid:
        return None

    return TenantContext(
        phone_number_id=pid,
        access_token=token,
        name=None,
        system_prompt=None,
        catalog_csv_path=None,
    )


def _resolve_tenant(phone_number_id: str) -> TenantContext | None:
    if phone_number_id.strip():
        ctx = fetch_tenant_context(phone_number_id)

        if ctx is not None:
            return ctx

    legacy = _legacy_tenant_context()

    if legacy is None:
        return None

    if (
        not phone_number_id.strip()
        or phone_number_id.strip() == legacy.phone_number_id
    ):
        return legacy

    return None


def _build_ai_answer(
    user_text: str,
    *,
    system_prompt_override: str | None,
    catalog_csv_path: str | None,
) -> tuple[str, str]:

    text = user_text.strip()

    rows = load_properties_for_catalog_path(catalog_csv_path)

    hits = filter_properties(text, rows)

    catalog = format_catalog(hits)

    if not catalog:
        catalog = (
            "(sin coincidencias con el filtro simple; "
            "pedi mas detalles o propon ampliar criterios.)"
        )

    system_prompt = (
        (system_prompt_override or "").strip()
        or DEFAULT_SYSTEM_PROMPT
    )

    user_prompt = (
        f"Consulta del cliente: {text}\n\n"
        f"Catalogo (hasta 3 opciones):\n{catalog}"
    )

    return system_prompt, user_prompt


def _extract_incoming_messages(
    payload: dict[str, Any],
) -> list[tuple[str, str, str]]:

    incoming: list[tuple[str, str, str]] = []

    entries = payload.get("entry") or []

    for entry in entries:

        changes = entry.get("changes") or []

        for change in changes:

            value = change.get("value") or {}

            metadata = value.get("metadata") or {}

            phone_number_id = str(
                metadata.get("phone_number_id") or ""
            ).strip()

            contacts = value.get("contacts") or []

            contact_wa_id = (
                str((contacts[0] or {}).get("wa_id", ""))
                if contacts
                else ""
            )

            messages = value.get("messages") or []

            logger.info(
                "Webhook payload: messages=%s statuses=%s",
                len(messages),
                len(value.get("statuses") or []),
            )

            for msg in messages:

                sender = str(
                    msg.get("from") or contact_wa_id
                ).strip()

                msg_type = str(msg.get("type") or "")

                logger.info(
                    "Mensaje detectado type=%s from=%s",
                    msg_type,
                    sender,
                )

                if msg_type != "text":
                    logger.info(
                        "Mensaje ignorado por tipo no soportado: %s",
                        msg_type,
                    )
                    continue

                body = str(
                    (msg.get("text") or {}).get("body", "")
                ).strip()

                if sender and body:
                    incoming.append(
                        (
                            sender,
                            body,
                            phone_number_id,
                        )
                    )

    return incoming


@app.get("/meta/whatsapp")
def meta_webhook_verify(
    hub_mode: str | None = Query(
        default=None,
        alias="hub.mode",
    ),
    hub_verify_token: str | None = Query(
        default=None,
        alias="hub.verify_token",
    ),
    hub_challenge: str | None = Query(
        default=None,
        alias="hub.challenge",
    ),
) -> PlainTextResponse:

    logger.info("========== WEBHOOK VERIFY ==========")

    logger.info(
        "Webhook verify called mode=%s token=%s",
        hub_mode,
        hub_verify_token,
    )

    if (
        hub_mode == "subscribe"
        and validate_meta_verify_token(hub_verify_token or "")
    ):
        logger.info("Webhook verified OK")

        return PlainTextResponse(
            content=hub_challenge or "",
            status_code=200,
        )

    logger.warning("Webhook verify FAILED")

    raise HTTPException(
        status_code=403,
        detail="Meta verify token invalido",
    )


@app.post("/meta/whatsapp")
async def meta_webhook_post(request: Request):

    raw_body = await request.body()

    logger.info("========== WEBHOOK POST HIT ==========")
    logger.info("HEADERS=%s", dict(request.headers))

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        payload = {"raw": raw_body.decode("utf-8", errors="ignore")}

    logger.info("FULL PAYLOAD=%s", json.dumps(payload, indent=2))

    return {"ok": True}