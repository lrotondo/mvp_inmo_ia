from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.conversation_flow import Phase, handle_turn
from app.llm.institutional_classifier import InstitutionalCategory
from app.tenant_service import InstitutionalProfile


def test_handle_turn_institutional_during_visit_intake() -> None:
    capture = {
        "intake_answered": True,
        "visit_pending": True,
        "visit_prompt_sent": True,
        "visit_answered": False,
    }
    profile = InstitutionalProfile(
        office_hours="Lun a Vie 9 a 18hs",
        office_address="Av. Central 100",
        social_links="@inmobiliaria",
    )

    async def _run():
        with (
            patch(
                "app.institutional_flow.fetch_institutional_profile",
                return_value=profile,
            ),
            patch(
                "app.institutional_flow.classify_institutional_message",
                new_callable=AsyncMock,
                return_value=InstitutionalCategory.OFFICE_HOURS,
            ),
        ):
            result = await handle_turn(
                tenant_name="Test",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path="data/x.csv",
                system_prompt_override=None,
                capture_data=dict(capture),
                user_text="¿qué horario tienen de atención?",
                session_flow_path="alquiler",
                phone_number_id="pnid1",
                wa_id="54911",
            )
        assert result.phase == Phase.INSTITUTIONAL.value
        assert "horarios de atención" in result.text.lower()
        assert not result.capture_data.get("visit_answered")

    asyncio.run(_run())


def test_handle_turn_skips_institutional_for_listing_search() -> None:
    capture = {"intake_answered": True}
    profile = InstitutionalProfile(
        office_hours="Lun a Vie",
        office_address="Calle 1",
        social_links="@x",
    )

    async def _run():
        with (
            patch(
                "app.institutional_flow.fetch_institutional_profile",
                return_value=profile,
            ),
            patch(
                "app.institutional_flow.classify_institutional_message",
                new_callable=AsyncMock,
            ) as mock_classify,
            patch(
                "app.conversation_flow.chat_completion",
                new_callable=AsyncMock,
                return_value="ok",
            ),
            patch(
                "app.conversation_flow.pick_listing_properties",
                new_callable=AsyncMock,
                return_value=type("R", (), {"ids": [], "rows": [], "empty_reason": ""})(),
            ),
        ):
            result = await handle_turn(
                tenant_name="Test",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path="data/x.csv",
                system_prompt_override=None,
                capture_data=dict(capture),
                user_text="quiero ver mas opciones",
                session_flow_path="alquiler",
                phone_number_id="pnid1",
                wa_id="54911",
            )
        mock_classify.assert_not_awaited()
        assert result.phase != Phase.INSTITUTIONAL.value

    asyncio.run(_run())
