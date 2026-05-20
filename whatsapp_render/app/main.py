from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.catalog import get_catalog_for_flow
from app.conversation import (
    append_conversation_turn,
    build_model_messages,
    get_conversation_history,
)
from app.db import dispose_engine, get_engine, init_db
from app.deepseek_client import chat_completion
from app.flow_triggers import (
    apply_captacion_closing,
    apply_visit_handoff,
    parse_flow_alerts,
    process_flow_alerts,
    register_visit_lead_on_handoff_message,
    process_waitlist_registration,
    resolve_flow_alerts,
)
from app.waitlist import fetch_waitlist_rows, waitlist_rows_to_csv
from app.lead_context import extract_property_ref
from app.meta_auth import (
    validate_meta_signature,
    validate_meta_verify_token,
)
from app.leads import try_register_lead
from app.listing_delivery import deliver_bot_response
from app.prompts.flow_master import build_flow_system_prompt
from app.session_state import get_or_create_session, resolve_flow_path, save_session
from app.tenant_service import (
    TenantContext,
    fetch_tenant_context,
)
from app.webhook_dedup import claim_inbound_message_id

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
        "app.leads",
        "app.session_state",
        "app.flow_triggers",
    ):
        logging.getLogger(name).setLevel(logging.INFO)


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


def _waitlist_export_secret() -> str:
    return os.environ.get("WAITLIST_EXPORT_SECRET", "").strip()


def _waitlist_export_default_days() -> int:
    raw = os.environ.get("WAITLIST_EXPORT_DEFAULT_DAYS", "7").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 7


@app.get("/admin/waitlist/export.csv")
def export_waitlist_csv(
    phone_number_id: str = Query(..., min_length=1),
    days: int | None = Query(None, ge=1, le=365),
    include_all: int = Query(0, ge=0, le=1),
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> Response:
    secret = _waitlist_export_secret()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="WAITLIST_EXPORT_SECRET no configurado",
        )
    if (x_admin_secret or "").strip() != secret:
        raise HTTPException(status_code=401, detail="No autorizado")

    if get_engine() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada")

    period = days if days is not None else _waitlist_export_default_days()
    rows = fetch_waitlist_rows(
        phone_number_id=phone_number_id,
        days=period,
        include_all_statuses=bool(include_all),
    )
    csv_body = waitlist_rows_to_csv(rows)
    filename = f"waitlist_{phone_number_id}_{period}d.csv"
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


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
        catalog_rent_csv_path=None,
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


def _extract_incoming_messages(
    payload: dict[str, Any],
) -> list[tuple[str, str, str, str, str]]:

    incoming: list[tuple[str, str, str, str, str]] = []

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

            contact_name = ""
            if contacts:
                profile = (contacts[0] or {}).get("profile") or {}
                contact_name = str(profile.get("name") or "").strip()

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

                message_id = str(msg.get("id") or "").strip()

                if sender and body:
                    incoming.append(
                        (
                            sender,
                            body,
                            phone_number_id,
                            contact_name,
                            message_id,
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

    for wa_id, user_text, pnid, contact_name, message_id in incoming:

        if not claim_inbound_message_id(message_id):
            continue

        logger.info(
            "Procesando mensaje wa_id=%s pnid=%s message_id=%s name=%r text=%s",
            wa_id,
            pnid,
            (message_id or "")[:48],
            contact_name or None,
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

        session = await asyncio.to_thread(
            get_or_create_session,
            ctx.phone_number_id,
            wa_id,
        )

        if session.bot_paused:
            logger.info(
                "Bot pausado para wa_id=%s (humano atiende); omitiendo LLM",
                wa_id,
            )
            continue

        history = await asyncio.to_thread(
            get_conversation_history,
            ctx.phone_number_id,
            wa_id,
        )

        previous_flow_path = session.flow_path
        flow_path = resolve_flow_path(session, user_text, history)
        flow_just_switched = (
            previous_flow_path != flow_path
            and flow_path in ("compra", "alquiler")
        )
        await asyncio.to_thread(
            save_session,
            ctx.phone_number_id,
            wa_id,
            flow_path=flow_path,
        )

        row_count, catalog_block, catalog_path_used = get_catalog_for_flow(
            flow_path,
            ctx.catalog_csv_path,
            ctx.catalog_rent_csv_path,
        )
        logger.info(
            "Catalogo flow=%s path=%r rows=%s",
            flow_path,
            catalog_path_used,
            row_count,
        )
        if row_count:
            catalog_block = (
                f"({row_count} propiedades; elegí las más relevantes):\n{catalog_block}"
            )

        system_prompt = build_flow_system_prompt(
            tenant_name=ctx.name or "la inmobiliaria",
            flow_path=flow_path,
            catalog_block=catalog_block,
            system_prompt_override=ctx.system_prompt,
        )

        model_messages = build_model_messages(
            system_prompt,
            history,
            user_text,
        )

        logger.info(
            "Invocando LLM flow=%s history=%s messages=%s",
            flow_path,
            len(history),
            len(model_messages),
        )

        answer = await chat_completion(model_messages)

        clean_answer, raw_alerts, raw_waitlist_tag = parse_flow_alerts(answer)
        alerts, interest_classification = await resolve_flow_alerts(
            raw_alerts,
            history=history,
            current_user_text=user_text,
            flow_path=flow_path,
            ctx=ctx,
            flow_just_switched=flow_just_switched,
        )
        property_ref = extract_property_ref(
            "",
            flow_path=flow_path,
            catalog_sale_path=ctx.catalog_csv_path,
            catalog_rent_path=ctx.catalog_rent_csv_path,
            history=history,
            current_user_text=user_text,
            user_only=True,
        )
        if interest_classification and interest_classification.property_ref.strip():
            property_ref = interest_classification.property_ref.strip()
        clean_answer = apply_visit_handoff(
            clean_answer,
            alerts,
            property_ref=property_ref,
            flow_path=flow_path,
            current_user_text=user_text,
        )
        clean_answer = apply_captacion_closing(clean_answer, alerts)

        logger.info(
            "LLM respondio answer_len=%s raw_alerts=%s alerts=%s",
            len(clean_answer),
            raw_alerts,
            alerts,
        )

        outbound_for_client = await deliver_bot_response(
            access_token=ctx.access_token,
            phone_number_id=ctx.phone_number_id,
            to_wa_id=wa_id,
            message=clean_answer,
            catalog_csv_path=catalog_path_used,
        )

        try:
            await register_visit_lead_on_handoff_message(
                outbound_message=outbound_for_client,
                alerts=alerts,
                flow_path=flow_path,
                ctx=ctx,
                contact_name=contact_name or None,
                wa_id=wa_id,
                history=history,
                current_user_text=user_text,
                classification=interest_classification,
                session=session,
            )

            await process_flow_alerts(
                alerts=alerts,
                session=session,
                flow_path=flow_path,
                ctx=ctx,
                contact_name=contact_name or None,
                wa_id=wa_id,
                history=history,
                current_user_text=user_text,
                classification=interest_classification,
            )

            await process_waitlist_registration(
                has_waitlist_tag=raw_waitlist_tag,
                flow_path=flow_path,
                ctx=ctx,
                contact_name=contact_name or None,
                wa_id=wa_id,
                history=history,
                current_user_text=user_text,
            )

            if flow_path not in ("compra", "alquiler"):
                await try_register_lead(
                    phone_number_id=ctx.phone_number_id,
                    wa_id=wa_id,
                    contact_name=contact_name or None,
                    catalog_csv_path=ctx.catalog_csv_path,
                    catalog_rent_csv_path=ctx.catalog_rent_csv_path,
                    flow_path=flow_path,
                    current_user_text=user_text,
                    access_token=ctx.access_token,
                    history=history,
                    skip_if_flow_alert_registered=bool(alerts),
                )
        except Exception:
            logger.exception(
                "Error post-respuesta (alertas/lead/waitlist) wa_id=%s; "
                "el cliente ya recibio el mensaje",
                wa_id,
            )

        try:
            await asyncio.to_thread(
                append_conversation_turn,
                ctx.phone_number_id,
                wa_id,
                user_text,
                outbound_for_client,
            )
        except Exception:
            logger.exception("Error guardando historial wa_id=%s", wa_id)

        logger.info(
            "Respuesta enviada a wa_id=%s",
            wa_id,
        )

    return {"ok": True}