from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.turn_handler import TurnContext, TurnKind, TurnPlan, generate_turn_reply
from app.search_profile import SearchProfile


def test_generate_turn_reply_general_does_not_shadow_load_last_listing() -> None:
    """Regression: import local en rama DETAIL no debe romper GENERAL."""
    profile = SearchProfile(
        branch="alquiler",
        property_type="departamento",
        min_bedrooms=2,
        any_zone=True,
        intake_complete=True,
        intake_step=3,
    )
    plan = TurnPlan(
        kind=TurnKind.GENERAL,
        profile=profile,
        catalog_path_used="data/tenants/inmobiliaria_cowork_alquiler.csv",
        candidate_ids=["6", "5", "2"],
        row_count=3,
    )
    ctx = TurnContext(
        tenant_name="Test",
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
        capture_data={
            "last_listing": {
                "ids": ["6", "5", "2"],
                "catalog_path": plan.catalog_path_used,
            }
        },
    )

    async def _run() -> str:
        with patch(
            "app.conversation_flow.chat_completion",
            new_callable=AsyncMock,
            return_value="La opción 2 tiene pileta.",
        ):
            return await generate_turn_reply(
                ctx, "la opción 2 tiene pileta?", plan
            )

    result = asyncio.run(_run())
    assert "pileta" in result.lower()
