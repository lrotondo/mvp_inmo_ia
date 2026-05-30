from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from app.capture_flow import merge_outbound_capture_flags
from app.data_reset import clear_operational_chat_tables
from app.db import dispose_engine, get_engine, init_db
from app.leads import LeadType, try_register_flow_alert
from app.session_state import capture_summary_text
from app.waitlist import fetch_waitlist_rows, waitlist_rows_to_csv
from app.meta_auth import (
    validate_meta_signature,
    validate_meta_verify_token,
)
from app.listing_context import set_last_viewed_property
from app.listing_delivery import BotDeliveryResult, deliver_bot_response
from app.meta_client import MetaSendError
from app.pipeline.inbound import process_inbound_message
from app.session_lifecycle import (
    apply_session_restart,
    get_last_inbound_at,
    should_auto_restart_session,
    should_reset_session_next_day,
    touch_last_inbound_at,
)
from app.session_state import get_or_create_session, resolve_flow_path, save_session
from app.tenant_service import (
    TenantContext,
    fetch_tenant_context,
)
from app.webhook_dedup import claim_inbound_message_id
from app.onboarding import onboarding_router
from app.onboarding.account_update import process_account_update_webhook

logger = logging.getLogger(__name__)

_ALERT_TO_LEAD_TYPE: dict[str, LeadType] = {
    "ALERTA_VENTA": "venta",
    "ALERTA_ALQUILER": "alquiler",
    "ALERTA_CAPTACION_PROPIETARIO": "captacion",
}


async def _register_simple_alerts(
    *,
    alerts: list[str],
    flow_path: str,
    property_ref: str,
    ctx: TenantContext,
    contact_name: str | None,
    wa_id: str,
    user_text: str,
    capture_data: dict[str, Any] | None,
) -> None:
    summary = (user_text or "").strip()
    cap_summary = capture_summary_text(capture_data) if capture_data else None
    for tag in alerts:
        lead_type = _ALERT_TO_LEAD_TYPE.get(tag)
        if not lead_type:
            continue
        await try_register_flow_alert(
            lead_type=lead_type,
            phone_number_id=ctx.phone_number_id,
            wa_id=wa_id,
            contact_name=contact_name,
            property_ref=property_ref or "",
            interest_summary=summary,
            conversation_summary=summary,
            capture_summary=cap_summary,
            access_token=ctx.access_token,
        )


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
        "app.llm",
        "app.llm.deepseek",
        "app.conversation_flow",
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

_cors_origins = [
    o.strip()
    for o in os.environ.get("ONBOARDING_CORS_ORIGINS", "").split(",")
    if o.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(onboarding_router)


@app.get("/")
def root() -> dict[str, str]:
    logger.info("GET /")
    return {
        "service": "whatsapp_render",
        "health": "/health",
        "webhook": "/meta/whatsapp",
        "onboarding_config": "/api/onboarding/config",
        "reset_chat_data": "/reset-chat-data",
    }


@app.get("/health")
def health() -> dict[str, str]:
    logger.info("GET /health")

    return {
        "status": "ok",
        "db": "on" if get_engine() is not None else "off",
    }


@app.get("/reset-chat-data")
def reset_chat_data() -> dict[str, Any]:
    """
    Vacía chat_messages, chat_sessions, client_leads y client_waitlist.
    Endpoint público (sin autenticación).
    """
    logger.warning("GET /reset-chat-data — borrado de tablas operativas solicitado")
    if get_engine() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada")
    try:
        deleted = clear_operational_chat_tables()
    except Exception as exc:
        logger.exception("reset_chat_data falló")
        raise HTTPException(
            status_code=500,
            detail="No se pudieron vaciar las tablas",
        ) from exc
    return {"ok": True, "deleted": deleted}


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

    account_updates = await process_account_update_webhook(payload)
    if account_updates:
        logger.info("account_update procesados=%s", account_updates)

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

        last_inbound_at = get_last_inbound_at(
            session.capture_data,
            session.updated_at,
        )
        now = datetime.now(timezone.utc)
        if should_reset_session_next_day(last_inbound_at, now=now):
            session = apply_session_restart()
            flow_path = "nuevo"
            flow_just_switched = False
        elif should_auto_restart_session(
            session.capture_data,
            user_text,
            last_inbound_at,
            now=now,
        ):
            session = apply_session_restart()
            flow_path = "nuevo"
            flow_just_switched = False
        else:
            previous_flow_path = session.flow_path
            flow_path = resolve_flow_path(session, user_text)
            flow_just_switched = (
                previous_flow_path != flow_path
                and flow_path in ("compra", "alquiler")
            )

        await asyncio.to_thread(
            save_session,
            ctx.phone_number_id,
            wa_id,
            flow_path=flow_path,
            capture_data=session.capture_data,
        )

        turn_result = await process_inbound_message(
            ctx=ctx,
            session=session,
            flow_path=flow_path,
            user_text=user_text,
            flow_just_switched=flow_just_switched,
            wa_id=wa_id,
            contact_name=contact_name,
        )

        clean_answer = turn_result.clean_answer
        raw_alerts = turn_result.raw_alerts
        alerts = turn_result.alerts
        property_ref = turn_result.property_ref
        catalog_path_used = turn_result.catalog_path_used

        logger.info(
            "Turno kind=%s answer_len=%s raw_alerts=%s alerts=%s ids=%s",
            turn_result.plan_kind,
            len(clean_answer),
            raw_alerts,
            alerts,
            turn_result.candidate_ids,
        )

        delivery: BotDeliveryResult | None = None
        try:
            delivery = await deliver_bot_response(
                access_token=ctx.access_token,
                phone_number_id=ctx.phone_number_id,
                to_wa_id=wa_id,
                message=clean_answer,
                catalog_csv_path=catalog_path_used,
                current_user_text=user_text,
                flow_path=flow_path,
                catalog_sale_path=ctx.catalog_csv_path,
                catalog_rent_path=ctx.catalog_rent_csv_path,
                property_ref=property_ref,
                capture_data=turn_result.capture_data or session.capture_data,
                skip_property_delivery=turn_result.skip_property_delivery,
            )
            outbound_for_client = delivery.text
        except MetaSendError as exc:
            logger.error(
                "WhatsApp no entregado wa_id=%s transient=%s code=%s status=%s: %s",
                wa_id,
                exc.is_transient,
                exc.error_code,
                exc.status_code,
                exc,
            )
            outbound_for_client = clean_answer
        except Exception:
            logger.exception(
                "Error enviando respuesta WhatsApp wa_id=%s; webhook OK para evitar reenvío Meta",
                wa_id,
            )
            outbound_for_client = clean_answer

        capture_after_turn = merge_outbound_capture_flags(
            turn_result.capture_data or dict(session.capture_data),
            outbound_for_client,
        )
        capture_after_turn = touch_last_inbound_at(
            capture_after_turn,
            datetime.now(timezone.utc),
        )
        if delivery is not None and delivery.delivered_property_id:
            capture_after_turn = set_last_viewed_property(
                capture_after_turn,
                property_id=delivery.delivered_property_id,
                catalog_path=catalog_path_used,
                branch=flow_path,
            )
        await asyncio.to_thread(
            save_session,
            ctx.phone_number_id,
            wa_id,
            flow_path=flow_path,
            capture_data=capture_after_turn,
        )

        try:
            await _register_simple_alerts(
                alerts=alerts,
                flow_path=flow_path,
                property_ref=property_ref,
                ctx=ctx,
                contact_name=contact_name or None,
                wa_id=wa_id,
                user_text=user_text,
                capture_data=capture_after_turn,
            )
            if turn_result.visit_lead_type in ("venta", "alquiler"):
                await try_register_flow_alert(
                    lead_type=turn_result.visit_lead_type,
                    phone_number_id=ctx.phone_number_id,
                    wa_id=wa_id,
                    contact_name=contact_name,
                    property_ref=property_ref or "",
                    interest_summary=turn_result.visit_lead_interest_summary,
                    conversation_summary=turn_result.visit_lead_conversation_summary,
                    capture_summary=capture_summary_text(capture_after_turn),
                    access_token=ctx.access_token,
                )
        except Exception:
            logger.exception(
                "Error registrando alerta/lead wa_id=%s",
                wa_id,
            )

        logger.info(
            "Respuesta enviada a wa_id=%s",
            wa_id,
        )

    return {"ok": True}