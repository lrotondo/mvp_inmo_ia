from __future__ import annotations

import logging
import re
from typing import Literal

from app.conversation import HistoryTurn, format_history_plain
from app.leads import LeadType, try_register_flow_alert
from app.prompts.flow_master import CLOSING_CAPTACION_TEXT
from app.session_state import (
    SessionState,
    capture_is_complete,
    capture_summary_text,
    merge_capture_from_conversation,
    save_session,
)
from app.tenant_service import TenantContext

logger = logging.getLogger(__name__)

AlertTag = Literal["ALERTA_VENTA", "ALERTA_ALQUILER", "ALERTA_CAPTACION_PROPIETARIO"]

_ALERT_RE = re.compile(
    r"\[(ALERTA_VENTA|ALERTA_ALQUILER|ALERTA_CAPTACION_PROPIETARIO)\]",
    re.I,
)

_TAG_TO_LEAD_TYPE: dict[str, LeadType] = {
    "ALERTA_VENTA": "venta",
    "ALERTA_ALQUILER": "alquiler",
    "ALERTA_CAPTACION_PROPIETARIO": "captacion",
}


def parse_flow_alerts(text: str) -> tuple[str, list[AlertTag]]:
    tags: list[AlertTag] = []
    for match in _ALERT_RE.finditer(text):
        key = match.group(1).upper()
        if key in _TAG_TO_LEAD_TYPE and key not in tags:
            tags.append(key)  # type: ignore[arg-type]

    clean = _ALERT_RE.sub("", text)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, tags


def apply_captacion_closing(clean_text: str, alerts: list[AlertTag]) -> str:
    if "ALERTA_CAPTACION_PROPIETARIO" in alerts:
        return CLOSING_CAPTACION_TEXT
    return clean_text


async def process_flow_alerts(
    *,
    alerts: list[AlertTag],
    session: SessionState,
    flow_path: str,
    ctx: TenantContext,
    contact_name: str | None,
    wa_id: str,
    history: list[HistoryTurn],
    current_user_text: str,
) -> SessionState:
    capture = merge_capture_from_conversation(session, history, current_user_text)
    updated_session = session
    bot_paused = session.bot_paused
    conversation_text = format_history_plain(history)

    if alerts:
        for tag in alerts:
            lead_type = _TAG_TO_LEAD_TYPE[tag]
            capture_summary = capture_summary_text(capture) if lead_type == "captacion" else None
            interest = _interest_for_alert(lead_type, capture, conversation_text)
            try:
                await try_register_flow_alert(
                    lead_type=lead_type,
                    phone_number_id=ctx.phone_number_id,
                    wa_id=wa_id,
                    contact_name=contact_name,
                    property_ref="",
                    interest_summary=interest,
                    conversation_summary=conversation_text[:1200],
                    capture_summary=capture_summary,
                    access_token=ctx.access_token,
                )
            except Exception:
                logger.exception(
                    "Error registrando alerta flow %s wa_id=%s",
                    lead_type,
                    wa_id,
                )
            if lead_type == "captacion":
                bot_paused = True

    elif (
        flow_path == "captacion"
        and capture_is_complete(capture)
        and not session.bot_paused
    ):
        logger.info("Captacion completa sin tag; alerta de respaldo wa_id=%s", wa_id)
        summary = capture_summary_text(capture)
        try:
            await try_register_flow_alert(
                lead_type="captacion",
                phone_number_id=ctx.phone_number_id,
                wa_id=wa_id,
                contact_name=contact_name,
                property_ref="",
                interest_summary=f"Propietario quiere vender: {summary}",
                conversation_summary=conversation_text[:1200],
                capture_summary=summary,
                access_token=ctx.access_token,
            )
        except Exception:
            logger.exception("Error alerta captacion respaldo wa_id=%s", wa_id)
        bot_paused = True

    updated_session = save_session(
        ctx.phone_number_id,
        wa_id,
        flow_path=flow_path,  # type: ignore[arg-type]
        bot_paused=bot_paused,
        capture_data=capture,
    )
    return updated_session


def _interest_for_alert(
    lead_type: LeadType,
    capture: dict,
    conversation_text: str,
) -> str:
    if lead_type == "captacion":
        summary = capture_summary_text(capture)
        return summary or "Propietario interesado en vender / tasar su inmueble."
    if lead_type == "alquiler":
        return "Inquilino con interés concreto en alquiler (visita o propiedad específica)."
    return "Comprador con interés concreto en compra (visita o propiedad específica)."
