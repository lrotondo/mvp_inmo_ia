from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.conversation import HistoryTurn
from app.detail_media import enrich_detail_media_from_catalog
from app.flow_triggers import (
    apply_captacion_closing,
    apply_visit_handoff,
    parse_flow_alerts,
    resolve_flow_alerts,
)
from app.property_matching import extract_property_ref
from app.listing_delivery import (
    ensure_listado_from_candidates,
    suppress_premature_catalog_outbound,
)
from app.session_state import SessionState
from app.turn_handler import (
    TurnContext,
    TurnKind,
    generate_turn_reply,
    plan_turn,
    session_capture_with_profile,
)
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


async def process_inbound_message(
    *,
    ctx: TenantContext,
    session: SessionState,
    flow_path: str,
    history: list[HistoryTurn],
    user_text: str,
    flow_just_switched: bool,
) -> InboundTurnResult:
    turn_ctx = TurnContext(
        tenant_name=ctx.name or "la inmobiliaria",
        flow_path=flow_path,
        catalog_sale_path=ctx.catalog_csv_path,
        catalog_rent_path=ctx.catalog_rent_csv_path,
        system_prompt_override=ctx.system_prompt,
    )
    plan = plan_turn(turn_ctx, history, user_text)

    answer = await generate_turn_reply(turn_ctx, history, user_text, plan)

    clean_answer, raw_alerts, has_waitlist_tag = parse_flow_alerts(answer)
    alerts, interest_classification = await resolve_flow_alerts(
        raw_alerts,
        history=history,
        current_user_text=user_text,
        flow_path=flow_path,
        ctx=ctx,
        flow_just_switched=flow_just_switched,
    )

    property_ref = plan.property_ref
    if interest_classification and interest_classification.property_ref.strip():
        property_ref = interest_classification.property_ref.strip()
    if not property_ref:
        property_ref = extract_property_ref(
            "",
            flow_path=flow_path,
            catalog_sale_path=ctx.catalog_csv_path,
            catalog_rent_path=ctx.catalog_rent_csv_path,
            history=history,
            current_user_text=user_text,
            user_only=True,
        )

    clean_answer = apply_visit_handoff(
        clean_answer,
        alerts,
        property_ref=property_ref,
        flow_path=flow_path,
        current_user_text=user_text,
    )
    clean_answer = apply_captacion_closing(clean_answer, alerts)

    if plan.kind == TurnKind.LISTING and plan.candidate_ids:
        clean_answer = ensure_listado_from_candidates(
            clean_answer,
            plan.candidate_ids,
            plan.catalog_path_used,
        )
    elif plan.kind != TurnKind.LISTING:
        clean_answer = suppress_premature_catalog_outbound(
            clean_answer,
            history=history,
            current_user_text=user_text,
            flow_path=flow_path,
        )

    clean_answer = enrich_detail_media_from_catalog(
        clean_answer,
        catalog_csv_path=plan.catalog_path_used,
        property_ref=property_ref,
        current_user_text=user_text,
        flow_path=flow_path,
        history=history,
        catalog_sale_path=ctx.catalog_csv_path,
        catalog_rent_path=ctx.catalog_rent_csv_path,
    )

    capture_data: dict[str, Any] | None = None
    if plan.profile and flow_path in ("compra", "alquiler"):
        capture_data = session_capture_with_profile(session, plan.profile, flow_path)

    logger.info(
        "turn_done kind=%s profile_complete=%s candidate_ids=%s path=%r",
        plan.kind.value,
        plan.profile.is_complete if plan.profile else None,
        plan.candidate_ids,
        plan.catalog_path_used,
    )

    return InboundTurnResult(
        clean_answer=clean_answer,
        raw_alerts=raw_alerts,
        alerts=alerts,
        interest_classification=interest_classification,
        property_ref=property_ref,
        plan_kind=plan.kind.value,
        candidate_ids=plan.candidate_ids,
        catalog_path_used=plan.catalog_path_used,
        capture_data=capture_data,
        has_waitlist_tag=has_waitlist_tag,
    )
