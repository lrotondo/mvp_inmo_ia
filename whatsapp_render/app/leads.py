from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select

from app.db import get_engine, session_scope
from app.email_client import send_email, smtp_configured
from app.meta_client import send_whatsapp_text_message
from app.models import ClientLead
from app.tenant_service import fetch_lead_notification_settings

logger = logging.getLogger(__name__)

LeadType = Literal["venta", "alquiler", "captacion"]


def _lead_detection_enabled() -> bool:
    raw = os.environ.get("LEAD_DETECTION_ENABLED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


_TRANSCRIPT_SUMMARY_RE = re.compile(
    r"^(cliente|usuario|user)\s*:\s*",
    re.I | re.M,
)


def is_transcript_summary(text: str) -> bool:
    """True si el texto parece un volcado tipo 'Cliente: ...' (no usar en notificaciones)."""
    body = (text or "").strip()
    if not body:
        return True
    hits = len(_TRANSCRIPT_SUMMARY_RE.findall(body))
    lines = [ln for ln in body.splitlines() if ln.strip()]
    return hits >= 2 or (hits >= 1 and len(lines) <= 3)


def format_lead_notification_subject(lead_type: LeadType) -> str:
    label = {"venta": "Compra", "alquiler": "Alquiler", "captacion": "Captación"}.get(
        lead_type, lead_type
    )
    return f"Lead {label} - nuevo interés"


def format_lead_notification_message(
    *,
    lead_type: LeadType,
    contact_name: str | None,
    wa_id: str,
    property_ref: str | None,
    interest_summary: str,
    conversation_summary: str,
    capture_summary: str | None = None,
) -> str:
    label = {"venta": "Compra", "alquiler": "Alquiler", "captacion": "Captación"}.get(
        lead_type, lead_type
    )
    name = (contact_name or "").strip() or "Sin nombre"
    prop = (property_ref or "").strip()
    lines = [
        f"🔔 Lead {label}",
        f"Cliente: {name} ({wa_id})",
    ]
    if prop:
        lines.append(f"Propiedad: {prop}")
    if interest_summary.strip():
        lines.append(f"Interés: {interest_summary.strip()}")
    if conversation_summary.strip() and not is_transcript_summary(conversation_summary):
        lines.append(f"Resumen: {conversation_summary.strip()}")
    if capture_summary and capture_summary.strip():
        lines.append(f"Datos captados: {capture_summary.strip()}")
    return "\n".join(lines)


def _upsert_lead(
    *,
    phone_number_id: str,
    wa_id: str,
    contact_name: str | None,
    property_ref: str,
    lead_type: LeadType,
    interest_summary: str,
    conversation_summary: str,
    capture_summary: str | None,
    conversation_at: datetime,
) -> bool:
    pnid = phone_number_id.strip()
    wid = wa_id.strip()
    prop = property_ref.strip() or None
    cutoff = conversation_at - timedelta(hours=24)

    with session_scope() as session:
        stmt = (
            select(ClientLead)
            .where(
                ClientLead.phone_number_id == pnid,
                ClientLead.wa_id == wid,
                ClientLead.lead_type == lead_type,
                ClientLead.conversation_at >= cutoff,
            )
            .order_by(ClientLead.conversation_at.desc())
        )
        existing = session.scalars(stmt).first()

        if existing is not None:
            existing.contact_name = contact_name or existing.contact_name
            existing.property_ref = prop
            existing.lead_type = lead_type
            existing.interest_summary = interest_summary
            existing.conversation_summary = conversation_summary
            existing.capture_summary = capture_summary
            existing.conversation_at = conversation_at
            logger.info(
                "Lead actualizado id=%s wa_id=%s lead_type=%s",
                existing.id,
                wid,
                lead_type,
            )
            return False

        row = ClientLead(
            phone_number_id=pnid,
            wa_id=wid,
            contact_name=contact_name,
            property_ref=prop,
            lead_type=lead_type,
            capture_summary=capture_summary,
            interest_summary=interest_summary,
            conversation_summary=conversation_summary,
            conversation_at=conversation_at,
        )
        session.add(row)
        logger.info("Lead creado wa_id=%s lead_type=%s", wid, lead_type)
        return True


async def _notify_agent_whatsapp(
    *,
    lead_type: LeadType,
    access_token: str,
    phone_number_id: str,
    notify_to: str,
    contact_name: str | None,
    wa_id: str,
    property_ref: str,
    interest_summary: str,
    conversation_summary: str,
    capture_summary: str | None = None,
) -> None:
    body = format_lead_notification_message(
        lead_type=lead_type,
        contact_name=contact_name,
        wa_id=wa_id,
        property_ref=property_ref or None,
        interest_summary=interest_summary,
        conversation_summary=conversation_summary,
        capture_summary=capture_summary,
    )
    await send_whatsapp_text_message(
        access_token=access_token,
        phone_number_id=phone_number_id,
        to_wa_id=notify_to,
        message=body,
    )
    logger.info("Notificacion lead WhatsApp enviada a %s (cliente wa_id=%s)", notify_to, wa_id)


async def _notify_agent_email(
    *,
    lead_type: LeadType,
    notify_to: str,
    contact_name: str | None,
    wa_id: str,
    property_ref: str,
    interest_summary: str,
    conversation_summary: str,
    capture_summary: str | None = None,
) -> None:
    if not smtp_configured():
        logger.warning(
            "SMTP no configurado; omitiendo email de lead a %s wa_id=%s",
            notify_to,
            wa_id,
        )
        return
    body = format_lead_notification_message(
        lead_type=lead_type,
        contact_name=contact_name,
        wa_id=wa_id,
        property_ref=property_ref or None,
        interest_summary=interest_summary,
        conversation_summary=conversation_summary,
        capture_summary=capture_summary,
    )
    subject = format_lead_notification_subject(lead_type)
    await send_email(to=notify_to, subject=subject, body_text=body)
    logger.info("Notificacion lead email enviada a %s (cliente wa_id=%s)", notify_to, wa_id)


async def try_register_flow_alert(
    *,
    lead_type: LeadType,
    phone_number_id: str,
    wa_id: str,
    contact_name: str | None,
    property_ref: str,
    interest_summary: str,
    conversation_summary: str,
    capture_summary: str | None,
    access_token: str,
    notify_on_update: bool = False,
) -> None:
    if not _lead_detection_enabled():
        return
    if get_engine() is None:
        logger.warning("Flow alert sin DATABASE_URL wa_id=%s", wa_id)
        return

    now = datetime.now(timezone.utc)
    is_new = await asyncio.to_thread(
        _upsert_lead,
        phone_number_id=phone_number_id,
        wa_id=wa_id,
        contact_name=contact_name,
        property_ref=property_ref,
        lead_type=lead_type,
        interest_summary=interest_summary,
        conversation_summary=conversation_summary,
        capture_summary=capture_summary,
        conversation_at=now,
    )

    if not is_new and not notify_on_update:
        return

    settings = await asyncio.to_thread(
        fetch_lead_notification_settings,
        phone_number_id,
    )
    if settings is None:
        logger.warning(
            "Sin configuracion de alertas para tenant phone_number_id=%r wa_id=%s",
            phone_number_id,
            wa_id,
        )
        return

    summary = interest_summary
    if not is_new and notify_on_update:
        summary = f"[Actualización de interés] {interest_summary}"

    token = access_token.strip()

    if settings.whatsapp_enabled and settings.whatsapp_to and token:
        try:
            await _notify_agent_whatsapp(
                lead_type=lead_type,
                access_token=token,
                phone_number_id=phone_number_id,
                notify_to=settings.whatsapp_to,
                contact_name=contact_name,
                wa_id=wa_id,
                property_ref=property_ref,
                interest_summary=summary,
                conversation_summary=conversation_summary,
                capture_summary=capture_summary,
            )
        except Exception:
            logger.exception(
                "Error enviando notificacion WhatsApp lead %s a %s",
                lead_type,
                settings.whatsapp_to,
            )

    if settings.email_enabled and settings.email:
        try:
            await _notify_agent_email(
                lead_type=lead_type,
                notify_to=settings.email,
                contact_name=contact_name,
                wa_id=wa_id,
                property_ref=property_ref,
                interest_summary=summary,
                conversation_summary=conversation_summary,
                capture_summary=capture_summary,
            )
        except Exception:
            logger.exception(
                "Error enviando notificacion email lead %s a %s",
                lead_type,
                settings.email,
            )
