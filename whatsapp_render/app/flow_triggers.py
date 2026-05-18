from __future__ import annotations

import logging
import re
from typing import Literal

from app.conversation import HistoryTurn, format_history_plain
from app.lead_context import (
    conversation_requests_human,
    conversation_wants_visit,
    conversation_wants_visit_rent,
    extract_property_ref,
    format_user_messages_plain,
    lead_type_from_flow_path,
    should_suppress_visit_alerts,
    user_messages_for_flow,
    user_signals_real_interest_current_message,
    user_signals_real_interest_rent_current_message,
)
from app.leads import LeadClassification, LeadType, evaluate_lead_interest, try_register_flow_alert
from app.waitlist import register_waitlist_entry
from app.waitlist_context import qualifies_for_waitlist_registration
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

_WAITLIST_TAG_RE = re.compile(r"\[LISTA_ESPERA\]", re.I)


def parse_flow_alerts(text: str) -> tuple[str, list[AlertTag], bool]:
    tags: list[AlertTag] = []
    for match in _ALERT_RE.finditer(text):
        key = match.group(1).upper()
        if key in _TAG_TO_LEAD_TYPE and key not in tags:
            tags.append(key)  # type: ignore[arg-type]

    has_waitlist = bool(_WAITLIST_TAG_RE.search(text))
    clean = _ALERT_RE.sub("", text)
    clean = _WAITLIST_TAG_RE.sub("", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, tags, has_waitlist


def filter_waitlist_tag(
    has_waitlist_tag: bool,
    current_user_text: str,
) -> bool:
    if not has_waitlist_tag:
        return False
    if qualifies_for_waitlist_registration(current_user_text):
        return True
    logger.info("LISTA_ESPERA descartada (sin aceptacion explicita del cliente)")
    return False


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


def filter_alerts_by_flow_path(
    alerts: list[AlertTag],
    flow_path: str,
) -> list[AlertTag]:
    """Descarta tags que no corresponden a la rama activa (ej. ALERTA_ALQUILER en compra)."""
    path = (flow_path or "").strip().lower()
    if path not in ("compra", "alquiler"):
        return alerts
    expected = "ALERTA_VENTA" if path == "compra" else "ALERTA_ALQUILER"
    kept: list[AlertTag] = []
    for tag in alerts:
        if tag in _VISIT_ALERT_TAGS and tag != expected:
            logger.info(
                "Alerta %s descartada (no coincide con flow_path=%s)",
                tag,
                path,
            )
            continue
        kept.append(tag)
    return kept


def filter_alerts_suppressed_for_browse(
    alerts: list[AlertTag],
    current_user_text: str,
    *,
    flow_just_switched: bool = False,
) -> list[AlertTag]:
    if not alerts or not should_suppress_visit_alerts(
        current_user_text, flow_just_switched=flow_just_switched
    ):
        return alerts
    kept: list[AlertTag] = []
    for tag in alerts:
        if tag in _VISIT_ALERT_TAGS:
            logger.info(
                "Alerta %s descartada (browse o cambio de rama)",
                tag,
            )
            continue
        kept.append(tag)
    return kept


async def resolve_flow_alerts(
    alerts: list[AlertTag],
    *,
    history: list[HistoryTurn],
    current_user_text: str,
    flow_path: str,
    ctx: TenantContext,
    flow_just_switched: bool = False,
) -> tuple[list[AlertTag], LeadClassification | None]:
    """Evalúa interés real y filtra banderas de compra/alquiler."""
    path = (flow_path or "").strip().lower()
    classification: LeadClassification | None = None

    has_visit_alert = bool(_VISIT_ALERT_TAGS.intersection(alerts))
    if has_visit_alert:
        classification = await evaluate_lead_interest(
            history=history,
            current_user_text=current_user_text,
            flow_path=flow_path,
            catalog_csv_path=ctx.catalog_csv_path,
            catalog_rent_csv_path=ctx.catalog_rent_csv_path,
            flow_just_switched=flow_just_switched,
        )

    filtered = filter_alerts_by_real_interest(alerts, classification)
    filtered = filter_alerts_by_flow_path(filtered, flow_path)
    filtered = filter_alerts_suppressed_for_browse(
        filtered,
        current_user_text,
        flow_just_switched=flow_just_switched,
    )

    if (
        path == "alquiler"
        and not filtered
        and user_signals_real_interest_rent_current_message(current_user_text)
    ):
        classification = classification or await evaluate_lead_interest(
            history=history,
            current_user_text=current_user_text,
            flow_path=flow_path,
            catalog_csv_path=ctx.catalog_csv_path,
            catalog_rent_csv_path=ctx.catalog_rent_csv_path,
            flow_just_switched=flow_just_switched,
        )
        if classification and classification.is_real_interest:
            logger.info(
                "Alerta ALERTA_ALQUILER de respaldo (LLM omitio bandera, visita/asesor confirmado)"
            )
            filtered = ["ALERTA_ALQUILER"]

    return filtered, classification


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
    current_user_text: str = "",
) -> str:
    if not _VISIT_ALERT_TAGS.intersection(alerts):
        return clean_text
    path = (flow_path or "").strip().lower()
    if path == "alquiler" and "ALERTA_ALQUILER" in alerts:
        return clean_text
    if path == "compra" and "ALERTA_VENTA" in alerts:
        if not user_signals_real_interest_current_message(current_user_text):
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
    user_messages = user_messages_for_flow(history, current_user_text, flow_path)
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
    visit_fn = (
        conversation_wants_visit_rent
        if lead_type == "alquiler"
        else conversation_wants_visit
    )
    if visit_fn(user_blob):
        parts.append("Pide visitar o ver un inmueble.")
    elif conversation_requests_human(user_blob):
        parts.append("Pide que lo contacte un asesor humano.")
    else:
        parts.append("Mostró interés concreto en una propiedad del catálogo.")
    if prop:
        parts.append(f"Referencia: {prop}.")
    parts.append("El bot no agendó día ni horario; debe contactarlo un asesor.")
    return " ".join(parts)


async def process_waitlist_registration(
    *,
    has_waitlist_tag: bool,
    flow_path: str,
    ctx: TenantContext,
    contact_name: str | None,
    wa_id: str,
    history: list[HistoryTurn],
    current_user_text: str,
) -> None:
    path = (flow_path or "").strip().lower()
    if path not in ("compra", "alquiler"):
        return
    if not filter_waitlist_tag(has_waitlist_tag, current_user_text):
        return
    try:
        is_new = await register_waitlist_entry(
            phone_number_id=ctx.phone_number_id,
            wa_id=wa_id,
            contact_name=contact_name,
            flow_path=flow_path,
            history=history,
            current_user_text=current_user_text,
            catalog_csv_path=ctx.catalog_csv_path,
            catalog_rent_csv_path=ctx.catalog_rent_csv_path,
        )
        logger.info(
            "Waitlist registrado wa_id=%s flow=%s is_new=%s",
            wa_id,
            flow_path,
            is_new,
        )
    except Exception:
        logger.exception("Error registrando waitlist wa_id=%s", wa_id)
