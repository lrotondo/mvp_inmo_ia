from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import get_engine, session_scope
from app.llm.deepseek import chat_completion
from app.models import ClientWaitlist


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


def requirements_from_text_fallback(
    *,
    waitlist_raw_text: str,
    seek_type: str,
    intake_text: str = "",
    listing_summary: str = "",
) -> WaitlistRequirements:
    text = (waitlist_raw_text or intake_text or "").strip()
    summary_parts = [p for p in (text, listing_summary) if p]
    summary = ". ".join(summary_parts) or "Requisitos según conversación del cliente."
    return WaitlistRequirements(
        zona="",
        presupuesto="",
        ambientes="",
        preferencias=text[:500],
        notas=listing_summary[:300],
        requirements_summary=summary[:800],
        conversation_summary=summary[:800],
    )


# Alias compat
requirements_from_profile_fallback = requirements_from_text_fallback


async def summarize_waitlist_requirements(
    *,
    seek_type: str,
    waitlist_raw_text: str,
    intake_text: str = "",
    listing_summary: str = "",
    log_context: dict | None = None,
) -> WaitlistRequirements:
    """Resume requisitos desde la respuesta libre del cliente a la pregunta bundle."""
    system = (
        "Sos un asistente de lista de espera inmobiliaria. El cliente rechazó las opciones "
        "mostradas y describió en un mensaje todo lo que busca. "
        "Respondé SOLO JSON válido con claves: zona, presupuesto, ambientes, preferencias, "
        "notas, requirements_summary, conversation_summary. "
        "requirements_summary: resumen claro para el equipo (2-4 oraciones). "
        "conversation_summary: mismo criterio en prosa. "
        "Extraé solo lo que el cliente indicó; no inventes datos."
    )
    user = (
        f"Rama: {seek_type}\n\n"
        f"### Respuesta del cliente (requisitos completos)\n{waitlist_raw_text}\n\n"
        f"### Contexto opcional — búsqueda inicial\n{intake_text or '(sin dato)'}\n\n"
        f"### Opciones que ya vio y rechazó\n{listing_summary or '(sin detalle)'}"
    )
    ctx = dict(log_context or {})
    ctx["prompt_source"] = "waitlist_summarize"
    try:
        raw = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=400,
            log_context=ctx,
        )
        parsed = _parse_classifier_json(raw)
        if parsed:
            return parsed
    except RuntimeError:
        pass
    return requirements_from_text_fallback(
        waitlist_raw_text=waitlist_raw_text,
        seek_type=seek_type,
        intake_text=intake_text,
        listing_summary=listing_summary,
    )


async def classify_waitlist_requirements(
    *,
    seek_type: str,
    intake_text: str,
    user_messages: str,
    listing_summary: str = "",
    waitlist_raw_text: str = "",
    log_context: dict | None = None,
) -> WaitlistRequirements:
    """Compat: delega a summarize si hay waitlist_raw_text."""
    if (waitlist_raw_text or "").strip():
        return await summarize_waitlist_requirements(
            seek_type=seek_type,
            waitlist_raw_text=waitlist_raw_text,
            intake_text=intake_text,
            listing_summary=listing_summary,
            log_context=log_context,
        )
    return requirements_from_text_fallback(
        waitlist_raw_text=user_messages,
        seek_type=seek_type,
        intake_text=intake_text,
        listing_summary=listing_summary,
    )


def register_waitlist_entry(
    *,
    phone_number_id: str,
    wa_id: str,
    contact_name: str | None,
    seek_type: str,
    requirements: WaitlistRequirements,
) -> bool:
    if get_engine() is None:
        return False
    pnid = phone_number_id.strip()
    wid = wa_id.strip()
    stype = (seek_type or "compra").strip().lower()
    if not pnid or not wid:
        return False

    values = {
        "phone_number_id": pnid,
        "wa_id": wid,
        "contact_name": (contact_name or "").strip() or None,
        "seek_type": stype,
        "status": "active",
        "requirements_json": requirements.to_json(),
        "requirements_summary": requirements.requirements_summary,
        "conversation_summary": requirements.conversation_summary,
    }

    try:
        with session_scope() as session:
            existing = session.scalar(
                select(ClientWaitlist).where(
                    ClientWaitlist.phone_number_id == pnid,
                    ClientWaitlist.wa_id == wid,
                    ClientWaitlist.seek_type == stype,
                    ClientWaitlist.status == "active",
                )
            )
            now = datetime.now(timezone.utc)
            if existing is not None:
                existing.contact_name = values["contact_name"]
                existing.requirements_json = values["requirements_json"]
                existing.requirements_summary = values["requirements_summary"]
                existing.conversation_summary = values["conversation_summary"]
                existing.updated_at = now
            else:
                session.add(
                    ClientWaitlist(
                        phone_number_id=pnid,
                        wa_id=wid,
                        contact_name=values["contact_name"],
                        seek_type=stype,
                        status="active",
                        requirements_json=values["requirements_json"],
                        requirements_summary=values["requirements_summary"],
                        conversation_summary=values["conversation_summary"],
                        created_at=now,
                        updated_at=now,
                    )
                )
    except RuntimeError:
        return False
    return True


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
