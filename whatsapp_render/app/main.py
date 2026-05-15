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
    "Eres 'Santi', un asesor inmobiliario experto de la ciudad de Tandil. "
    "Tu tono es profesional pero cercano (estilo tandilense), educado y eficiente. "
    "\n\nREGLAS DE ORO:\n"
    "1. Usa emojis de forma moderada para ser amigable (ej: 🏠,📍,✅).\n"
    "2. Si el cliente pregunta por una zona, destaca beneficios locales (ej: 'cerca del Calvario', 'zona Uncas', 'vistas a las sierras').\n"
    "3. RESPUESTA BREVE: En WhatsApp la gente no lee párrafos largos. Usa viñetas (bullet points).\n"
    "4. DATOS ESTRICTOS: Solo usa la información del catálogo provisto. Si no tienes el dato (ej. precio o m2), di: 'No tengo ese detalle aquí conmigo, pero puedo consultarlo con el equipo'.\n"
    "5. CIERRE: Siempre termina con una pregunta para mantener la charla viva (ej: ¿Te gustaría ir a verla? o ¿Buscás en alguna zona en especial?).\n"
    "6. PROHIBIDO: No inventes propiedades, precios ni direcciones."
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
async def meta_webhook_post(request: Request) -> dict[str, bool]:
    _client = request.client.host if request.client else None
    logger.info(
        "POST /meta/whatsapp enter client=%s content_type=%s "
        "content_length=%s x_hub_sig256_present=%s",
        _client,
        request.headers.get("content-type", ""),
        request.headers.get("content-length", ""),
        bool(request.headers.get("X-Hub-Signature-256")),
    )
    raw_body = await request.body()

    signature = request.headers.get(
        "X-Hub-Signature-256",
        "",
    )

    logger.info(
        "POST /meta/whatsapp body_bytes=%s signature_present=%s",
        len(raw_body),
        bool(signature),
    )

    try:
        raw_text = raw_body.decode("utf-8")
        logger.info("RAW BODY: %s", raw_text)
    except Exception as ex:
        logger.warning("No se pudo loguear raw body: %s", ex)

    #
    # VALIDACION DE FIRMA
    # IMPORTANTE:
    # En desarrollo puede convenir deshabilitarla
    #
    META_VALIDATE_SIGNATURE = (
        os.environ.get(
            "META_VALIDATE_SIGNATURE",
            "false",
        ).lower()
        == "true"
    )

    logger.info(
        "META_VALIDATE_SIGNATURE=%s",
        META_VALIDATE_SIGNATURE,
    )

    if META_VALIDATE_SIGNATURE:

        if signature and not validate_meta_signature(
            raw_body,
            signature,
        ):
            has_secret = bool(
                os.environ.get(
                    "META_APP_SECRET",
                    "",
                ).strip()
            )

            logger.warning(
                "Firma Meta rechazada (403): "
                "META_APP_SECRET configurado=%s "
                "signature_length=%s "
                "body_bytes=%s",
                has_secret,
                len(signature.strip()),
                len(raw_body),
            )

            raise HTTPException(
                status_code=403,
                detail="Firma Meta invalida",
            )

    try:
        payload = json.loads(raw_body.decode("utf-8"))

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:

        logger.warning("JSON invalido: %s", exc)

        raise HTTPException(
            status_code=400,
            detail="Payload invalido",
        ) from exc

    logger.info(
        "Payload object=%s",
        payload.get("object"),
    )

    incoming = _extract_incoming_messages(payload)

    logger.info(
        "Mensajes de texto extraidos=%s",
        len(incoming),
    )

    if not incoming:
        logger.info(
            "Nada que procesar "
            "(sin mensajes text o payload solo status)."
        )

    for wa_id, user_text, pnid in incoming:

        logger.info(
            "Procesando mensaje wa_id=%s pnid=%s text=%s",
            wa_id,
            pnid,
            user_text,
        )

        ctx = await asyncio.to_thread(
            _resolve_tenant,
            pnid,
        )

        if ctx is None:

            logger.warning(
                "Sin tenant para phone_number_id=%r "
                "(from=%r)",
                pnid,
                wa_id,
            )

            continue

        system_prompt, user_prompt = _build_ai_answer(
            user_text,
            system_prompt_override=ctx.system_prompt,
            catalog_csv_path=ctx.catalog_csv_path,
        )

        logger.info("Invocando LLM")

        answer = await chat_completion(
            [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ]
        )

        logger.info(
            "LLM respondio answer_len=%s",
            len(answer),
        )

        await send_whatsapp_text_message(
            access_token=ctx.access_token,
            phone_number_id=ctx.phone_number_id,
            to_wa_id=wa_id,
            message=answer,
        )

        logger.info(
            "Respuesta enviada a wa_id=%s",
            wa_id,
        )

    return {"ok": True}