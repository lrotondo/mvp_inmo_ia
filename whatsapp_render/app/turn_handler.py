"""
Fachada de compatibilidad: la lógica vive en app.conversation_flow.
"""

from __future__ import annotations

from typing import Any

from app.conversation_flow import (
    FlowContext as TurnContext,
    FlowPlan as TurnPlan,
    Phase as TurnKind,
    build_detail_outbound as _build_detail_outbound,
    build_reply as generate_turn_reply,
    decide_phase,
    plan_message as plan_turn,
)


async def build_detail_outbound(
    user_text: str,
    *,
    listing_rows: list,
) -> str:
    return _build_detail_outbound(user_text, listing_rows=listing_rows)


from app.search_profile import SearchProfile, merge_search_profile_into_capture as session_capture_with_profile


def resolve_turn_kind(
    flow_path: str,
    *,
    profile: SearchProfile | None,
    current_user_text: str,
    capture_data: dict[str, Any] | None = None,
    catalog_path_used: str | None = None,
) -> TurnKind:
    return TurnKind(
        decide_phase(
            flow_path,
            profile=profile,
            user_text=current_user_text,
            capture_data=capture_data,
            catalog_path=catalog_path_used,
        ).value
    )


__all__ = [
    "TurnKind",
    "TurnContext",
    "TurnPlan",
    "plan_turn",
    "generate_turn_reply",
    "resolve_turn_kind",
    "build_detail_outbound",
    "session_capture_with_profile",
]
