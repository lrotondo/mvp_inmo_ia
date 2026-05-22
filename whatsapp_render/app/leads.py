from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select

from app.catalog import get_catalog_for_flow, get_catalog_search_terms
from app.lead_context import (
    conversation_requests_human,
    conversation_wants_visit,
    conversation_wants_visit_rent,
    extract_property_ref,
    format_conversation_for_classifier,
    format_user_messages_plain,
    lead_type_from_flow_path,
    build_rent_visit_lead_notes,
    qualifies_for_lead_notification,
    rent_visit_ready_for_alert,
    user_signals_real_interest_current_message,
)
from app.conversation import HistoryTurn, format_history_plain, get_conversation_history
from app.db import get_engine, session_scope
from app.groq_client import chat_completion
from app.meta_client import send_whatsapp_text_message
from app.models import ClientLead

logger = logging.getLogger(__name__)

_ALQUILER_RE = re.compile(r"\b(alquilar|alquiler|inquilino|renta)\b", re.I)

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

_CLASSIFIER_SYSTEM_BASE = (
    "Sos un analista de leads inmobiliarios. "
    "Evaluá SOLO lo que escribió el CLIENTE (líneas 'Cliente:'). "
    "Ignorá por completo requisitos, precios o propiedades que solo aparezcan en el catálogo "
    "o que el asesor bot haya sugerido sin confirmación del cliente. "
    "Respondé ÚNICAMENTE con un objeto JSON válido (sin markdown, sin texto extra) "
    "con estas claves exactas:\n"
    '- "is_real_interest": boolean\n'
    '- "property_ref": string (ID o dirección del catálogo SOLO si el cliente la nombró; "" si no)\n'
    '- "interest_summary": string (1-2 oraciones en español sobre lo que EL CLIENTE dijo)\n'
    '- "conversation_summary": string (2-4 oraciones en prosa para un asesor humano; '
    "sintetizá zona, presupuesto, tipo de búsqueda y pedidos concretos del cliente; "
    "**prohibido** copiar líneas ni usar el formato \"Cliente: ...\")\n\n"
    "is_real_interest=true solo si el CLIENTE, con sus palabras, muestra intención clara: "
    "visitar, reservar, negociar, pedir un asesor humano, o elegir una propiedad concreta "
    "(ID, dirección o 'me interesa esa/la de X'). "
    "is_real_interest=false si solo saluda, pide ver opciones genéricas "
    "('decime qué tenés', 'qué hay', 'mostrame'), explora sin elegir, o no nombró una propiedad."
)

_CLASSIFIER_ALQUILER_NOTE = (
    "\n\nContexto: flujo ALQUILER (inquilino). "
    "is_real_interest=true si pide visitar/ver inmuebles, hablar con asesor humano, "
    "o ya indicó preferencia horaria (mañana/tarde/fin de semana) tras pedir visita. "
    "Incluí en conversation_summary la preferencia horaria si la mencionó. "
    "is_real_interest=false si solo explora, pide más opciones o elige favorita "
    "sin pedir visita ni dar franja horaria tras la consulta del bot."
)


def _classifier_system_for_flow(flow_path: str) -> str:
    base = _CLASSIFIER_SYSTEM_BASE
    if (flow_path or "").strip().lower() == "alquiler":
        return base + _CLASSIFIER_ALQUILER_NOTE
    return base

_DEFAULT_LEAD_MODEL = "llama-3.1-8b-instant"

LeadType = Literal["venta", "alquiler", "captacion"]


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
    lead_type: LeadType,
    contact_name: str | None,
    wa_id: str,
    property_ref: str | None,
    interest_summary: str,
    conversation_summary: str,
    capture_summary: str | None = None,
) -> str:
    name = (contact_name or "").strip() or "Sin nombre"
    prop = (property_ref or "").strip()
    prop_line = f"Propiedad: {prop}\n" if prop else ""
    interest = interest_summary.strip()[:800]
    convo = conversation_summary.strip()[:1200]
    type_labels = {
        "venta": "COMPRA / VENTA",
        "alquiler": "ALQUILER",
        "captacion": "CAPTACIÓN (propietario)",
    }
    headers = {
        "venta": "🔔 Lead comprador — venta",
        "alquiler": "🔔 Lead inquilino — alquiler",
        "captacion": "🔔 Captación — propietario quiere vender",
    }
    header = headers.get(lead_type, "🔔 Nuevo lead inmobiliario")
    capture_line = ""
    if capture_summary and capture_summary.strip():
        capture_line = f"\nDatos del inmueble:\n{capture_summary.strip()[:600]}\n"
    tipo = type_labels.get(lead_type, lead_type.upper())
    return (
        f"{header}\n"
        f"Tipo de operación: {tipo}\n\n"
        f"Cliente: {name}\n"
        f"WhatsApp: {wa_id}\n"
        f"{prop_line}"
        f"{capture_line}\n"
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
    *,
    flow_path: str = "compra",
) -> bool:
    branch = (flow_path or "compra").strip().lower()
    terms = get_catalog_search_terms(catalog_csv_path, branch=branch)
    if _text_has_lead_signals(current_user_text, terms):
        return True
    for turn in history:
        if turn.role == "user" and _text_has_lead_signals(turn.content, terms):
            return True
    return False


_TRANSCRIPT_LINE_RE = re.compile(r"^\s*cliente\s*:", re.I | re.M)

_SUMMARIZER_SYSTEM = (
    "Sos un asesor inmobiliario. Recibís los mensajes del cliente (a veces con prefijo "
    "'Cliente:'). Escribí un resumen de 2 a 4 oraciones en español, en tercera persona, "
    "para que un colega humano entienda qué busca sin leer el chat entero. "
    "Incluí: intención (compra/alquiler), zona o barrio, presupuesto si lo dijo, "
    "propiedad u opción de interés, y pedidos concretos (fotos, visita, asesor). "
    "Respondé solo el resumen en prosa, sin JSON, sin viñetas, sin copiar mensajes línea a línea."
)


def is_transcript_summary(text: str) -> bool:
    """Detecta si el texto es transcripción cruda en lugar de resumen."""
    body = text.strip()
    if not body:
        return True
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) < 2:
        return "cliente:" in body.lower()[:80]
    client_lines = sum(1 for ln in lines if _TRANSCRIPT_LINE_RE.match(ln))
    return client_lines >= 2 or client_lines >= len(lines) // 2


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


async def classify_interest(
    conversation_text: str,
    catalog_excerpt: str,
    *,
    flow_path: str = "compra",
) -> LeadClassification | None:
    user_content = (
        f"Catálogo (referencia):\n{catalog_excerpt[:2500]}\n\n"
        f"Conversación:\n{conversation_text[:4000]}"
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": _classifier_system_for_flow(flow_path)},
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


async def summarize_user_conversation(
    user_conversation: str,
    *,
    flow_path: str = "compra",
) -> str:
    """Resumen en prosa vía LLM (fallback cuando el clasificador devuelve transcripción)."""
    text = user_conversation.strip()
    if not text:
        return ""
    branch = (flow_path or "compra").strip().lower()
    raw = await chat_completion(
        [
            {"role": "system", "content": _SUMMARIZER_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Rama del flujo: {branch}\n\n"
                    f"Mensajes del cliente:\n{text[:3500]}"
                ),
            },
        ],
        model=_lead_model(),
        max_tokens=280,
        temperature=0.2,
    )
    summary = raw.strip()
    if summary.startswith("```"):
        summary = re.sub(r"^```(?:\w+)?\s*", "", summary)
        summary = re.sub(r"\s*```$", "", summary).strip()
    return summary[:1200]


async def ensure_intelligent_conversation_summary(
    conversation_summary: str,
    user_conversation: str,
    *,
    flow_path: str = "compra",
) -> str:
    candidate = conversation_summary.strip()
    if candidate and not is_transcript_summary(candidate):
        return candidate[:1200]
    synthesized = await summarize_user_conversation(
        user_conversation, flow_path=flow_path
    )
    if synthesized:
        return synthesized
    return user_conversation.strip()[:1200]


def _apply_lead_qualification_gate(
    classification: LeadClassification | None,
    *,
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
    catalog_csv_path: str | None,
    catalog_rent_csv_path: str | None,
    flow_just_switched: bool = False,
) -> LeadClassification | None:
    if classification is None or not classification.is_real_interest:
        return classification
    if qualifies_for_lead_notification(
        history,
        current_user_text,
        flow_path=flow_path,
        catalog_sale_path=catalog_csv_path,
        catalog_rent_path=catalog_rent_csv_path,
        flow_just_switched=flow_just_switched,
    ):
        return classification
    logger.info(
        "Lead descartado (puerta determinista): clasificador=true pero sin intencion concreta del cliente"
    )
    return LeadClassification(
        is_real_interest=False,
        property_ref="",
        interest_summary=classification.interest_summary,
        conversation_summary=classification.conversation_summary,
    )


async def evaluate_lead_interest(
    *,
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
    catalog_csv_path: str | None,
    catalog_rent_csv_path: str | None,
    flow_just_switched: bool = False,
) -> LeadClassification | None:
    """Clasifica interés real (misma barra para alertas de flujo y leads)."""
    branch = (flow_path or "compra").strip().lower()
    user_conversation = format_conversation_for_classifier(
        history, current_user_text, flow_path=branch
    )
    conversation_summary = user_conversation[:1200]

    _count, catalog_excerpt, _used = get_catalog_for_flow(
        branch,
        catalog_csv_path,
        catalog_rent_csv_path,
    )
    classification = await classify_interest(
        user_conversation, catalog_excerpt, flow_path=branch
    )
    classification = _apply_lead_qualification_gate(
        classification,
        history=history,
        current_user_text=current_user_text,
        flow_path=flow_path,
        catalog_csv_path=catalog_csv_path,
        catalog_rent_csv_path=catalog_rent_csv_path,
        flow_just_switched=flow_just_switched,
    )
    if classification is not None and classification.is_real_interest:
        smart_summary = await ensure_intelligent_conversation_summary(
            classification.conversation_summary,
            user_conversation,
            flow_path=branch,
        )
        if smart_summary != classification.conversation_summary:
            classification = LeadClassification(
                is_real_interest=classification.is_real_interest,
                property_ref=classification.property_ref,
                interest_summary=classification.interest_summary,
                conversation_summary=smart_summary,
            )
        return classification

    has_signals = (
        rent_visit_ready_for_alert(history, current_user_text, flow_path)
        if branch == "alquiler"
        else user_signals_real_interest_current_message(current_user_text)
    )
    if not has_signals:
        return classification

    if not qualifies_for_lead_notification(
        history,
        current_user_text,
        flow_path=flow_path,
        catalog_sale_path=catalog_csv_path,
        catalog_rent_path=catalog_rent_csv_path,
        flow_just_switched=flow_just_switched,
    ):
        return classification

    prop = extract_property_ref(
        "",
        flow_path=flow_path,
        catalog_sale_path=catalog_csv_path,
        catalog_rent_path=catalog_rent_csv_path,
        history=history,
        current_user_text=current_user_text,
        user_only=True,
    )
    summary_parts: list[str] = []
    if branch == "alquiler":
        rent_notes = build_rent_visit_lead_notes(
            history, current_user_text, flow_path
        )
        if rent_notes:
            summary_parts.append(rent_notes)
        elif conversation_requests_human(current_user_text):
            summary_parts.append("Cliente pide contacto con un asesor humano.")
        else:
            summary_parts.append("Cliente listo para coordinar visita (alquiler).")
    else:
        current = current_user_text.strip()
        if conversation_wants_visit(current):
            summary_parts.append("Cliente pide visitar o ver un inmueble.")
        if conversation_requests_human(current):
            summary_parts.append("Cliente pide contacto con un asesor humano.")
        if not summary_parts:
            summary_parts.append("Cliente muestra interés concreto según señales del mensaje.")
    if prop:
        summary_parts.append(f"Referencia del catálogo: {prop}.")
    smart_summary = await ensure_intelligent_conversation_summary(
        "",
        user_conversation,
        flow_path=branch,
    )
    if branch == "alquiler":
        rent_notes = build_rent_visit_lead_notes(
            history, current_user_text, flow_path
        )
        if rent_notes and rent_notes not in smart_summary:
            smart_summary = (
                f"{smart_summary}\n\n{rent_notes}".strip()
                if smart_summary.strip()
                else rent_notes
            )
    return LeadClassification(
        is_real_interest=True,
        property_ref=prop,
        interest_summary=" ".join(summary_parts),
        conversation_summary=smart_summary,
    )


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
    logger.info("Notificacion lead enviada a %s (cliente wa_id=%s)", notify_to, wa_id)


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

    if not _lead_whatsapp_notify_enabled():
        return

    notify_to = _lead_whatsapp_notify_to()
    if not notify_to:
        return

    token = access_token.strip()
    if not token:
        return

    summary = interest_summary
    if not is_new and notify_on_update:
        summary = f"[Actualización de interés] {interest_summary}"

    try:
        await _notify_agent_whatsapp(
            lead_type=lead_type,
            access_token=token,
            phone_number_id=phone_number_id,
            notify_to=notify_to,
            contact_name=contact_name,
            wa_id=wa_id,
            property_ref=property_ref,
            interest_summary=summary,
            conversation_summary=conversation_summary,
            capture_summary=capture_summary,
        )
    except Exception:
        logger.exception(
            "Error enviando notificacion flow %s a %s",
            lead_type,
            notify_to,
        )


async def try_register_lead(
    *,
    phone_number_id: str,
    wa_id: str,
    contact_name: str | None,
    catalog_csv_path: str | None,
    catalog_rent_csv_path: str | None = None,
    flow_path: str = "compra",
    current_user_text: str,
    access_token: str,
    history: list[HistoryTurn] | None = None,
    skip_if_flow_alert_registered: bool = False,
) -> None:
    if not _lead_detection_enabled():
        return
    if get_engine() is None:
        return
    if skip_if_flow_alert_registered:
        logger.debug("Lead classifier omitido (alerta de flujo ya registrada) wa_id=%s", wa_id)
        return

    if history is None:
        history = get_conversation_history(phone_number_id, wa_id, limit=4)
    if not history:
        return

    if not any(t.role == "user" for t in history):
        return

    branch = (flow_path or "compra").strip().lower()
    catalog_for_signals = (
        catalog_rent_csv_path if branch == "alquiler" else catalog_csv_path
    )
    if not should_run_lead_classifier(
        current_user_text, history, catalog_for_signals, flow_path=branch
    ):
        logger.info("Lead omitido (sin señales en mensaje/historial) wa_id=%s", wa_id)
        return

    classification = await evaluate_lead_interest(
        history=history,
        current_user_text=current_user_text,
        flow_path=flow_path,
        catalog_csv_path=catalog_csv_path,
        catalog_rent_csv_path=catalog_rent_csv_path,
    )
    if classification is None or not classification.is_real_interest:
        if classification is not None:
            logger.info("Lead no registrado (sin interes real) wa_id=%s", wa_id)
        return

    if not classification.interest_summary or not classification.conversation_summary:
        logger.warning("Lead incompleto wa_id=%s", wa_id)
        return

    now = datetime.now(timezone.utc)
    lead_type = lead_type_from_flow_path(flow_path)
    property_ref = (classification.property_ref or "").strip()
    if not property_ref:
        property_ref = extract_property_ref(
            "",
            flow_path=flow_path,
            catalog_sale_path=catalog_csv_path,
            catalog_rent_path=catalog_rent_csv_path,
            history=history,
            current_user_text=current_user_text,
            user_only=True,
        )

    is_new = await asyncio.to_thread(
        _upsert_lead,
        phone_number_id=phone_number_id,
        wa_id=wa_id,
        contact_name=contact_name,
        property_ref=property_ref,
        lead_type=lead_type,
        interest_summary=classification.interest_summary,
        conversation_summary=classification.conversation_summary,
        capture_summary=None,
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
            lead_type=lead_type,
            access_token=token,
            phone_number_id=phone_number_id,
            notify_to=notify_to,
            contact_name=contact_name,
            wa_id=wa_id,
            property_ref=property_ref,
            interest_summary=classification.interest_summary,
            conversation_summary=classification.conversation_summary,
        )
    except Exception:
        logger.exception(
            "Error enviando notificacion WhatsApp del lead a %s",
            notify_to,
        )
