from __future__ import annotations

import logging
import re
from typing import Literal

from app.conversation import HistoryTurn, format_history_plain
from app.lead_context import (
    conversation_requests_human,
    conversation_wants_visit,
    extract_property_ref,
    format_user_messages_plain,
    lead_type_from_flow_path,
)
from app.leads import LeadClassification, LeadType, evaluate_lead_interest, try_register_flow_alert
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

_VISIT_ALERT_TAGS: frozenset[str] = frozenset({"ALERTA_VENTA", "ALERTA_ALQUILER"})


def parse_flow_alerts(text: str) -> tuple[str, list[AlertTag]]:
    tags: list[AlertTag] = []
    for match in _ALERT_RE.finditer(text):
        key = match.group(1).upper()
        if key in _TAG_TO_LEAD_TYPE and key not in tags:
            tags.append(key)  # type: ignore[arg-type]

    clean = _ALERT_RE.sub("", text)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, tags


def filter_alerts_by_real_interest(
    alerts: list[AlertTag],
    classification: LeadClassification | None,
) -> list[AlertTag]:
    """Descarta [ALERTA_VENTA]/[ALERTA_ALQUILER] si no hay interés real confirmado."""
    if not alerts:
        return []
    valid: list[AlertTag] = []
    for tag in alerts:
        if tag == "ALERTA_CAPTACION_PROPIETARIO":
            valid.append(tag)
            continue
        if tag in _VISIT_ALERT_TAGS:
            if classification and classification.is_real_interest:
                valid.append(tag)
            else:
                logger.info(
                    "Alerta %s descartada (sin interes real confirmado)",
                    tag,
                )
            continue
        valid.append(tag)
    return valid


async def resolve_flow_alerts(
    alerts: list[AlertTag],
    *,
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
    ctx: TenantContext,
) -> tuple[list[AlertTag], LeadClassification | None]:
    """Evalúa interés real y filtra banderas de compra/alquiler."""
    if not alerts:
        return [], None
    has_visit_alert = bool(_VISIT_ALERT_TAGS.intersection(alerts))
    classification: LeadClassification | None = None
    if has_visit_alert:
        classification = await evaluate_lead_interest(
            history=history,
            current_user_text=current_user_text,
            flow_path=flow_path,
            catalog_csv_path=ctx.catalog_csv_path,
            catalog_rent_csv_path=ctx.catalog_rent_csv_path,
        )
    return filter_alerts_by_real_interest(alerts, classification), classification


def apply_captacion_closing(clean_text: str, alerts: list[AlertTag]) -> str:
    if "ALERTA_CAPTACION_PROPIETARIO" in alerts:
        return CLOSING_CAPTACION_TEXT
    return clean_text


def apply_visit_handoff(
    clean_text: str,
    alerts: list[AlertTag],
    *,
    property_ref: str,
    flow_path: str,
) -> str:
    if not _VISIT_ALERT_TAGS.intersection(alerts):
        return clean_text
    path = (flow_path or "").strip().lower()
    if path == "alquiler" and "ALERTA_ALQUILER" in alerts:
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
    classification: LeadClassification | None = None,
) -> SessionState:
    capture = merge_capture_from_conversation(session, history, current_user_text)
    bot_paused = session.bot_paused
    conversation_text = format_history_plain(history)
    full_text = (
        f"{conversation_text}\nCliente: {current_user_text}"
        if conversation_text
        else f"Cliente: {current_user_text}"
    )
    user_messages = format_user_messages_plain(history, current_user_text)
    property_ref = extract_property_ref(
        "",
        flow_path=flow_path,
        catalog_sale_path=ctx.catalog_csv_path,
        catalog_rent_path=ctx.catalog_rent_csv_path,
        history=history,
        current_user_text=current_user_text,
        user_only=True,
    )
    if classification and classification.property_ref.strip():
        property_ref = classification.property_ref.strip()

    if alerts:
        for tag in alerts:
            lead_type = _lead_type_for_alert(tag, flow_path)
            capture_summary = capture_summary_text(capture) if lead_type == "captacion" else None
            interest = _interest_for_alert(
                lead_type,
                capture,
                property_ref,
                flow_path,
                classification=classification,
                user_messages_text=user_messages,
            )
            summary = (
                classification.conversation_summary.strip()
                if classification and classification.conversation_summary.strip()
                else full_text[:1200]
            )
            try:
                await try_register_flow_alert(
                    lead_type=lead_type,
                    phone_number_id=ctx.phone_number_id,
                    wa_id=wa_id,
                    contact_name=contact_name,
                    property_ref=property_ref,
                    interest_summary=interest,
                    conversation_summary=summary,
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

    return save_session(
        ctx.phone_number_id,
        wa_id,
        flow_path=flow_path,  # type: ignore[arg-type]
        bot_paused=bot_paused,
        capture_data=capture,
    )


def _interest_for_alert(
    lead_type: LeadType,
    capture: dict,
    property_ref: str,
    flow_path: str,
    *,
    classification: LeadClassification | None = None,
    user_messages_text: str = "",
) -> str:
    if lead_type == "captacion":
        summary = capture_summary_text(capture)
        return summary or "Propietario interesado en vender / tasar su inmueble."

    if classification and classification.interest_summary.strip():
        return classification.interest_summary.strip()

    op = "alquiler" if lead_type == "alquiler" else "compra/venta"
    prop = (property_ref or "").strip()
    parts: list[str] = [f"Cliente en rama {flow_path} ({op})."]
    user_blob = user_messages_text.strip()
    if conversation_wants_visit(user_blob):
        parts.append("Pide visitar o ver un inmueble.")
    elif conversation_requests_human(user_blob):
        parts.append("Pide que lo contacte un asesor humano.")
    else:
        parts.append("Mostró interés concreto en una propiedad del catálogo.")
    if prop:
        parts.append(f"Referencia: {prop}.")
    parts.append("El bot no agendó día ni horario; debe contactarlo un asesor.")
    return " ".join(parts)
