from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.conversation_flow import handle_turn
from app.tenant_service import TenantContext

logger = logging.getLogger(__name__)


@dataclass
class InboundTurnResult:
    clean_answer: str
    raw_alerts: list[str]
    alerts: list[str]
    interest_classification: Any
    property_ref: str
    plan_kind: str
    candidate_ids: list[str]
    catalog_path_used: str | None
    capture_data: dict[str, Any] | None
    has_waitlist_tag: bool = False
    bot_paused: bool = False


async def process_inbound_message(
    *,
    ctx: TenantContext,
    session,
    flow_path: str,
    user_text: str,
    flow_just_switched: bool,
    wa_id: str = "",
    contact_name: str | None = None,
) -> InboundTurnResult:
    result = await handle_turn(
        tenant_name=ctx.name or "la inmobiliaria",
        flow_path=flow_path,
        catalog_sale_path=ctx.catalog_csv_path,
        catalog_rent_path=ctx.catalog_rent_csv_path,
        system_prompt_override=ctx.system_prompt,
        capture_data=dict(session.capture_data),
        user_text=user_text,
        session_flow_path=session.flow_path,
        flow_just_switched=flow_just_switched,
        phone_number_id=ctx.phone_number_id,
        wa_id=wa_id,
        contact_name=contact_name,
    )

    logger.info(
        "turn_done phase=%s ids=%s path=%r",
        result.phase,
        result.candidate_ids,
        result.catalog_path,
    )

    return InboundTurnResult(
        clean_answer=result.text,
        raw_alerts=list(result.alerts),
        alerts=list(result.alerts),
        interest_classification=None,
        property_ref=result.property_ref,
        plan_kind=result.phase,
        candidate_ids=result.candidate_ids,
        catalog_path_used=result.catalog_path,
        capture_data=result.capture_data,
        has_waitlist_tag=result.phase == "waitlist_confirm",
        bot_paused=result.bot_paused,
    )
