from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.conversation import format_history_plain, get_conversation_history
from app.db import get_engine, session_scope
from app.groq_client import chat_completion
from app.models import ClientLead

logger = logging.getLogger(__name__)

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
    "negociar precio, pedir asesor humano, o consulta específica sobre una propiedad/zona concreta. "
    "false si solo saluda, pregunta genérico sin compromiso, o no hay propiedad ni zona definida."
)


@dataclass(frozen=True)
class LeadClassification:
    is_real_interest: bool
    property_ref: str
    interest_summary: str
    conversation_summary: str


def _lead_detection_enabled() -> bool:
    raw = os.environ.get("LEAD_DETECTION_ENABLED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


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
        f"Catálogo (referencia de propiedades):\n{catalog_excerpt[:4000]}\n\n"
        f"Conversación:\n{conversation_text[:6000]}"
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": _CLASSIFIER_SYSTEM},
            {"role": "user", "content": user_content},
        ],
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
) -> None:
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
            return

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


async def try_register_lead(
    *,
    phone_number_id: str,
    wa_id: str,
    contact_name: str | None,
    catalog_csv_path: str | None,
) -> None:
    if not _lead_detection_enabled():
        return
    if get_engine() is None:
        return

    history = get_conversation_history(phone_number_id, wa_id, limit=20)
    if not history:
        return

    if not any(t.role == "user" for t in history):
        return

    from app.catalog import format_catalog, load_properties_for_catalog_path

    rows = load_properties_for_catalog_path(catalog_csv_path)
    catalog_excerpt = format_catalog(rows) or "(sin catálogo)"

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
    await asyncio.to_thread(
        _upsert_lead,
        phone_number_id=phone_number_id,
        wa_id=wa_id,
        contact_name=contact_name,
        property_ref=classification.property_ref,
        interest_summary=classification.interest_summary,
        conversation_summary=classification.conversation_summary,
        conversation_at=now,
    )
