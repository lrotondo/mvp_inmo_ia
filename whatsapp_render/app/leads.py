from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.catalog import get_cached_compact_catalog, get_catalog_search_terms
from app.conversation import HistoryTurn, format_history_plain, get_conversation_history
from app.db import get_engine, session_scope
from app.groq_client import chat_completion
from app.meta_client import send_whatsapp_text_message
from app.models import ClientLead

logger = logging.getLogger(__name__)

_INTEREST_KEYWORDS = re.compile(
    r"\b("
    r"visitar|visita|comprar|compra|alquilar|alquiler|reservar|reserva|"
    r"precio|negociar|financiaci[oó]n|asesor|coordinar|"
    r"interesad[oa]|me\s+interesa|quiero\s+ver|verla|verlo|"
    r"ubicaci[oó]n|d[oó]nde\s+queda|llamar|humano|persona|"
    r"hablar\s+con|comunicar|comunicarme|contacto|agente|vendedor"
    r")\b",
    re.I,
)

_CLASSIFIER_SYSTEM = (
    "Sos un analista de leads inmobiliarios. "
    "Evaluá si el cliente muestra interés real de compra o alquiler concreto. "
    "Respondé ÚNICAMENTE con un objeto JSON válido (sin markdown, sin texto extra) "
    "con estas claves exactas:\n"
    '- "is_real_interest": boolean\n'
    '- "property_ref": string (ID o dirección del catálogo; "" si no hay una concreta)\n'
    '- "interest_summary": string (1-2 oraciones en español sobre el interés y la propiedad)\n'
    '- "conversation_summary": string (2-4 oraciones resumiendo el hilo)\n\n'
    "is_real_interest=true solo si hay intención clara: visitar, comprar, reservar, "
    "negociar precio, pedir hablar con una persona/asesor, o consulta específica sobre una "
    "propiedad/zona concreta. "
    "false si solo saluda, pregunta genérico sin compromiso, o no hay propiedad ni zona definida."
)

_DEFAULT_LEAD_MODEL = "llama-3.1-8b-instant"


@dataclass(frozen=True)
class LeadClassification:
    is_real_interest: bool
    property_ref: str
    interest_summary: str
    conversation_summary: str


def _app_env() -> str:
    return (
        os.environ.get("APP_ENV", "").strip().lower()
        or os.environ.get("ENVIRONMENT", "").strip().lower()
    )


def _lead_detection_enabled() -> bool:
    if _app_env() in ("development", "dev", "local"):
        logger.debug("Lead detection desactivado (entorno %s)", _app_env())
        return False
    raw = os.environ.get("LEAD_DETECTION_ENABLED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _lead_model() -> str:
    return os.environ.get("GROQ_LEAD_MODEL", _DEFAULT_LEAD_MODEL).strip() or _DEFAULT_LEAD_MODEL


def _lead_whatsapp_notify_to() -> str:
    return re.sub(r"\D", "", os.environ.get("LEAD_WHATSAPP_NOTIFY_TO", "").strip())


def _lead_whatsapp_notify_enabled() -> bool:
    if not _lead_whatsapp_notify_to():
        return False
    raw = os.environ.get("LEAD_WHATSAPP_NOTIFY_ENABLED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def format_lead_notification_message(
    *,
    contact_name: str | None,
    wa_id: str,
    property_ref: str | None,
    interest_summary: str,
    conversation_summary: str,
) -> str:
    name = (contact_name or "").strip() or "Sin nombre"
    prop = (property_ref or "").strip()
    prop_line = f"Propiedad: {prop}\n" if prop else ""
    interest = interest_summary.strip()[:800]
    convo = conversation_summary.strip()[:1200]
    return (
        "🔔 Nuevo lead inmobiliario\n\n"
        f"Cliente: {name}\n"
        f"WhatsApp: {wa_id}\n"
        f"{prop_line}\n"
        f"Interés:\n{interest}\n\n"
        f"Resumen de la conversación:\n{convo}"
    )


def _text_has_lead_signals(text: str, catalog_terms: frozenset[str]) -> bool:
    body = text.strip().lower()
    if not body:
        return False
    if _INTEREST_KEYWORDS.search(body):
        return True
    for term in catalog_terms:
        if len(term) >= 4 and term in body:
            return True
    return False


def should_run_lead_classifier(
    current_user_text: str,
    history: list[HistoryTurn],
    catalog_csv_path: str | None,
) -> bool:
    terms = get_catalog_search_terms(catalog_csv_path)
    if _text_has_lead_signals(current_user_text, terms):
        return True
    for turn in history:
        if turn.role == "user" and _text_has_lead_signals(turn.content, terms):
            return True
    return False


def _parse_classifier_json(raw: str) -> LeadClassification | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    return LeadClassification(
        is_real_interest=bool(data.get("is_real_interest")),
        property_ref=str(data.get("property_ref") or "").strip(),
        interest_summary=str(data.get("interest_summary") or "").strip(),
        conversation_summary=str(data.get("conversation_summary") or "").strip(),
    )


async def _classify_interest(conversation_text: str, catalog_excerpt: str) -> LeadClassification | None:
    user_content = (
        f"Catálogo (referencia):\n{catalog_excerpt[:2500]}\n\n"
        f"Conversación:\n{conversation_text[:4000]}"
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": _CLASSIFIER_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        model=_lead_model(),
        max_tokens=400,
        temperature=0.1,
    )
    parsed = _parse_classifier_json(raw)
    if parsed is None:
        logger.warning("Lead classifier: JSON invalido raw=%s", raw[:500])
    return parsed


def _upsert_lead(
    *,
    phone_number_id: str,
    wa_id: str,
    contact_name: str | None,
    property_ref: str,
    interest_summary: str,
    conversation_summary: str,
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
                ClientLead.conversation_at >= cutoff,
            )
            .order_by(ClientLead.conversation_at.desc())
        )
        if prop:
            stmt = stmt.where(ClientLead.property_ref == prop)

        existing = session.scalars(stmt).first()

        if existing is not None:
            existing.contact_name = contact_name or existing.contact_name
            existing.property_ref = prop
            existing.interest_summary = interest_summary
            existing.conversation_summary = conversation_summary
            existing.conversation_at = conversation_at
            logger.info(
                "Lead actualizado id=%s wa_id=%s property_ref=%r",
                existing.id,
                wid,
                prop,
            )
            return False

        row = ClientLead(
            phone_number_id=pnid,
            wa_id=wid,
            contact_name=contact_name,
            property_ref=prop,
            interest_summary=interest_summary,
            conversation_summary=conversation_summary,
            conversation_at=conversation_at,
        )
        session.add(row)
        logger.info("Lead creado wa_id=%s property_ref=%r", wid, prop)
        return True


async def _notify_agent_whatsapp(
    *,
    access_token: str,
    phone_number_id: str,
    notify_to: str,
    contact_name: str | None,
    wa_id: str,
    property_ref: str,
    interest_summary: str,
    conversation_summary: str,
) -> None:
    body = format_lead_notification_message(
        contact_name=contact_name,
        wa_id=wa_id,
        property_ref=property_ref or None,
        interest_summary=interest_summary,
        conversation_summary=conversation_summary,
    )
    await send_whatsapp_text_message(
        access_token=access_token,
        phone_number_id=phone_number_id,
        to_wa_id=notify_to,
        message=body,
    )
    logger.info("Notificacion lead enviada a %s (cliente wa_id=%s)", notify_to, wa_id)


async def try_register_lead(
    *,
    phone_number_id: str,
    wa_id: str,
    contact_name: str | None,
    catalog_csv_path: str | None,
    current_user_text: str,
    access_token: str,
) -> None:
    if not _lead_detection_enabled():
        return
    if get_engine() is None:
        return

    history = get_conversation_history(phone_number_id, wa_id, limit=4)
    if not history:
        return

    if not any(t.role == "user" for t in history):
        return

    if not should_run_lead_classifier(current_user_text, history, catalog_csv_path):
        logger.info("Lead omitido (sin señales en mensaje/historial) wa_id=%s", wa_id)
        return

    _count, catalog_excerpt = get_cached_compact_catalog(catalog_csv_path)
    conversation_text = format_history_plain(history)
    classification = await _classify_interest(conversation_text, catalog_excerpt)
    if classification is None or not classification.is_real_interest:
        if classification is not None:
            logger.info("Lead no registrado (sin interes real) wa_id=%s", wa_id)
        return

    if not classification.interest_summary or not classification.conversation_summary:
        logger.warning("Lead incompleto wa_id=%s", wa_id)
        return

    now = datetime.now(timezone.utc)
    is_new = await asyncio.to_thread(
        _upsert_lead,
        phone_number_id=phone_number_id,
        wa_id=wa_id,
        contact_name=contact_name,
        property_ref=classification.property_ref,
        interest_summary=classification.interest_summary,
        conversation_summary=classification.conversation_summary,
        conversation_at=now,
    )

    if not is_new:
        return

    if not _lead_whatsapp_notify_enabled() or not _lead_detection_enabled():
        return

    notify_to = _lead_whatsapp_notify_to()
    if not notify_to:
        logger.debug("LEAD_WHATSAPP_NOTIFY_TO no configurado; omitiendo aviso WhatsApp")
        return

    token = access_token.strip()
    if not token:
        logger.warning("No se pudo notificar lead: access_token vacio")
        return

    try:
        await _notify_agent_whatsapp(
            access_token=token,
            phone_number_id=phone_number_id,
            notify_to=notify_to,
            contact_name=contact_name,
            wa_id=wa_id,
            property_ref=classification.property_ref,
            interest_summary=classification.interest_summary,
            conversation_summary=classification.conversation_summary,
        )
    except Exception:
        logger.exception(
            "Error enviando notificacion WhatsApp del lead a %s",
            notify_to,
        )
