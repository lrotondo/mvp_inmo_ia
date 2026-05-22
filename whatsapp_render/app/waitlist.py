from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import get_engine, session_scope
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
