from __future__ import annotations

import logging
import re
from typing import Literal

from app.conversation import HistoryTurn, format_history_plain
from app.lead_context import (
    extract_property_ref,
    lead_type_from_flow_path,
)
from app.leads import LeadType, try_register_flow_alert
from app.prompts.flow_master import CLOSING_CAPTACION_TEXT, format_visit_handoff
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


def apply_visit_handoff(
    clean_text: str,
    alerts: list[AlertTag],
    *,
    property_ref: str,
) -> str:
    visit_tags = {"ALERTA_VENTA", "ALERTA_ALQUILER"}
    if not visit_tags.intersection(alerts):
        return clean_text
    return format_visit_handoff(property_ref)


def _lead_type_for_alert(tag: AlertTag, flow_path: str) -> LeadType:
    mapped = _TAG_TO_LEAD_TYPE[tag]
    expected = lead_type_from_flow_path(flow_path)
    if flow_path in ("compra", "alquiler") and mapped != expected:
        logger.warning(
            "Tag %s no coincide con flow_path=%s; usando lead_type=%s",
            tag,
            flow_path,
            expected,
        )
        return expected
    return mapped


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
    full_text = f"{conversation_text}\nCliente: {current_user_text}"
    property_ref = extract_property_ref(
        full_text,
        flow_path=flow_path,
        catalog_sale_path=ctx.catalog_csv_path,
        catalog_rent_path=ctx.catalog_rent_csv_path,
    )

    if alerts:
        for tag in alerts:
            lead_type = _lead_type_for_alert(tag, flow_path)
            capture_summary = capture_summary_text(capture) if lead_type == "captacion" else None
            interest = _interest_for_alert(
                lead_type,
                capture,
                property_ref,
                flow_path,
            )
            try:
                await try_register_flow_alert(
                    lead_type=lead_type,
                    phone_number_id=ctx.phone_number_id,
                    wa_id=wa_id,
                    contact_name=contact_name,
                    property_ref=property_ref,
                    interest_summary=interest,
                    conversation_summary=full_text[:1200],
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
    property_ref: str,
    flow_path: str,
) -> str:
    if lead_type == "captacion":
        summary = capture_summary_text(capture)
        return summary or "Propietario interesado en vender / tasar su inmueble."
    op = "alquiler" if lead_type == "alquiler" else "compra/venta"
    prop = (property_ref or "").strip()
    prop_clause = f" Propiedad: {prop}." if prop else ""
    return (
        f"Cliente en rama {flow_path} ({op}). Solicita coordinar visita; "
        f"el bot NO agendó día ni horario — debe contactarlo un asesor.{prop_clause}"
    )
