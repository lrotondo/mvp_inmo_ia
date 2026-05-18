from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select

from app.catalog import get_catalog_for_flow
from app.conversation import HistoryTurn
from app.db import get_engine, session_scope
from app.groq_client import chat_completion
from app.lead_context import format_conversation_for_classifier, user_messages_for_flow
from app.leads import _lead_detection_enabled, _lead_model
from app.models import ClientWaitlist
from app.waitlist_context import qualifies_for_waitlist_registration

logger = logging.getLogger(__name__)

SeekType = Literal["venta", "alquiler"]
WaitlistStatus = Literal["active", "contacted", "closed"]


def seek_type_from_flow_path(flow_path: str) -> SeekType | None:
    path = (flow_path or "").strip().lower()
    if path == "compra":
        return "venta"
    if path == "alquiler":
        return "alquiler"
    return None


_CLASSIFIER_SYSTEM = (
    "Sos un analista inmobiliario. Extraé los requisitos del CLIENTE para una lista de espera "
    "(avisar cuando aparezca una propiedad que encaje). "
    "Usá SOLO mensajes del cliente en la rama actual (compra o alquiler). "
    "Ignorá preferencias de otra operación si cambió de intención. "
    "Respondé ÚNICAMENTE con JSON válido (sin markdown) con estas claves:\n"
    '- "zona": string (barrios/zonas; "" si no dijo)\n'
    '- "presupuesto": string (monto y moneda si los dijo; "" si no)\n'
    '- "ambientes": string (cantidad o tipo; "" si no)\n'
    '- "preferencias": string (mascotas, garage, piso, etc.; "" si no)\n'
    '- "notas": string (cualquier otro detalle relevante)\n'
    '- "requirements_summary": string (2-4 oraciones en español, resumen legible para un asesor)\n'
    '- "conversation_summary": string (2-4 oraciones sobre lo que pidió el cliente en esta rama)\n'
)


@dataclass(frozen=True)
class WaitlistRequirements:
    zona: str
    presupuesto: str
    ambientes: str
    preferencias: str
    notas: str
    requirements_summary: str
    conversation_summary: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "zona": self.zona,
                "presupuesto": self.presupuesto,
                "ambientes": self.ambientes,
                "preferencias": self.preferencias,
                "notas": self.notas,
            },
            ensure_ascii=False,
        )


def _parse_classifier_json(raw: str) -> WaitlistRequirements | None:
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

    summary = str(data.get("requirements_summary") or "").strip()
    if not summary:
        parts = [
            str(data.get("zona") or "").strip(),
            str(data.get("presupuesto") or "").strip(),
            str(data.get("ambientes") or "").strip(),
            str(data.get("preferencias") or "").strip(),
            str(data.get("notas") or "").strip(),
        ]
        summary = ". ".join(p for p in parts if p) or "Requisitos según conversación."

    return WaitlistRequirements(
        zona=str(data.get("zona") or "").strip(),
        presupuesto=str(data.get("presupuesto") or "").strip(),
        ambientes=str(data.get("ambientes") or "").strip(),
        preferencias=str(data.get("preferencias") or "").strip(),
        notas=str(data.get("notas") or "").strip(),
        requirements_summary=summary,
        conversation_summary=str(data.get("conversation_summary") or "").strip()
        or summary,
    )


async def classify_waitlist_requirements(
    *,
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
    catalog_csv_path: str | None,
    catalog_rent_csv_path: str | None,
) -> WaitlistRequirements | None:
    branch = (flow_path or "").strip().lower()
    user_conversation = format_conversation_for_classifier(
        history, current_user_text, flow_path=branch
    )
    if not user_conversation.strip():
        scoped = user_messages_for_flow(history, current_user_text, branch)
        user_conversation = f"Cliente: {scoped}" if scoped.strip() else ""

    _count, catalog_excerpt, _used = get_catalog_for_flow(
        branch, catalog_csv_path, catalog_rent_csv_path
    )
    user_content = (
        f"Catálogo (referencia):\n{catalog_excerpt[:2000]}\n\n"
        f"Conversación:\n{user_conversation[:4000]}"
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": _CLASSIFIER_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        model=_lead_model(),
        max_tokens=500,
        temperature=0.1,
    )
    parsed = _parse_classifier_json(raw)
    if parsed is None:
        logger.warning("Waitlist classifier: JSON invalido raw=%s", raw[:500])
    return parsed


def _upsert_waitlist(
    *,
    phone_number_id: str,
    wa_id: str,
    contact_name: str | None,
    seek_type: SeekType,
    requirements: WaitlistRequirements,
) -> bool:
    pnid = phone_number_id.strip()
    wid = wa_id.strip()
    now = datetime.now(timezone.utc)

    with session_scope() as session:
        existing = session.scalars(
            select(ClientWaitlist).where(
                ClientWaitlist.phone_number_id == pnid,
                ClientWaitlist.wa_id == wid,
                ClientWaitlist.seek_type == seek_type,
                ClientWaitlist.status == "active",
            )
        ).first()

        if existing is not None:
            existing.contact_name = contact_name or existing.contact_name
            existing.requirements_json = requirements.to_json()
            existing.requirements_summary = requirements.requirements_summary
            existing.conversation_summary = requirements.conversation_summary
            existing.updated_at = now
            logger.info(
                "Waitlist actualizado id=%s wa_id=%s seek_type=%s",
                existing.id,
                wid,
                seek_type,
            )
            return False

        row = ClientWaitlist(
            phone_number_id=pnid,
            wa_id=wid,
            contact_name=contact_name,
            seek_type=seek_type,
            status="active",
            requirements_json=requirements.to_json(),
            requirements_summary=requirements.requirements_summary,
            conversation_summary=requirements.conversation_summary,
        )
        session.add(row)
        logger.info("Waitlist creado wa_id=%s seek_type=%s", wid, seek_type)
        return True


async def register_waitlist_entry(
    *,
    phone_number_id: str,
    wa_id: str,
    contact_name: str | None,
    flow_path: str,
    history: list[HistoryTurn],
    current_user_text: str,
    catalog_csv_path: str | None,
    catalog_rent_csv_path: str | None,
) -> bool:
    if not _lead_detection_enabled():
        return False
    if get_engine() is None:
        logger.warning("Waitlist sin DATABASE_URL wa_id=%s", wa_id)
        return False

    seek_type = seek_type_from_flow_path(flow_path)
    if seek_type is None:
        return False

    if not qualifies_for_waitlist_registration(current_user_text):
        logger.info("Waitlist omitido (sin aceptacion explicita) wa_id=%s", wa_id)
        return False

    requirements = await classify_waitlist_requirements(
        history=history,
        current_user_text=current_user_text,
        flow_path=flow_path,
        catalog_csv_path=catalog_csv_path,
        catalog_rent_csv_path=catalog_rent_csv_path,
    )
    if requirements is None:
        requirements = WaitlistRequirements(
            zona="",
            presupuesto="",
            ambientes="",
            preferencias="",
            notas="",
            requirements_summary="Cliente en lista de espera (requisitos no estructurados).",
            conversation_summary=user_messages_for_flow(
                history, current_user_text, flow_path
            )[:1200],
        )

    return await asyncio.to_thread(
        _upsert_waitlist,
        phone_number_id=phone_number_id,
        wa_id=wa_id,
        contact_name=contact_name,
        seek_type=seek_type,
        requirements=requirements,
    )


def fetch_waitlist_rows(
    *,
    phone_number_id: str,
    days: int = 7,
    include_all_statuses: bool = False,
) -> list[ClientWaitlist]:
    if get_engine() is None:
        return []

    pnid = phone_number_id.strip()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))

    with session_scope() as session:
        stmt = select(ClientWaitlist).where(
            ClientWaitlist.phone_number_id == pnid,
            ClientWaitlist.created_at >= cutoff,
        )
        if not include_all_statuses:
            stmt = stmt.where(ClientWaitlist.status == "active")
        stmt = stmt.order_by(ClientWaitlist.created_at.desc())
        return list(session.scalars(stmt).all())


def waitlist_rows_to_csv(rows: list[ClientWaitlist]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "created_at",
            "updated_at",
            "seek_type",
            "status",
            "contact_name",
            "wa_id",
            "requirements_summary",
            "requirements_json",
            "conversation_summary",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.created_at.isoformat() if row.created_at else "",
                row.updated_at.isoformat() if row.updated_at else "",
                row.seek_type or "",
                row.status or "",
                row.contact_name or "",
                row.wa_id or "",
                row.requirements_summary or "",
                row.requirements_json or "",
                row.conversation_summary or "",
            ]
        )
    return buffer.getvalue()
