from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.conversation_flow import Phase, decide_phase, handle_turn
from app.search_profile import SearchProfile
from app.visit_flow import (
    get_visit_pending,
    get_visit_prompt_sent,
    is_visit_collecting,
    mark_visit_pending,
    mark_visit_prompt_sent,
    reset_visit_state,
)
from app.visit_lead import VisitLeadSummary


def _complete_profile() -> SearchProfile:
    return SearchProfile(
        branch="alquiler",
        property_types=("departamento",),
        zone_tokens=("centro",),
        any_zone=False,
        min_bedrooms=2,
        intake_complete=True,
    )


def test_decide_phase_visit_intake_when_pending() -> None:
    capture = mark_visit_pending(
        {},
        interest_text="me interesa, como puedo verla?",
        property_ref="Duplex Chacabuco",
    )
    phase = decide_phase(
        "alquiler",
        profile=_complete_profile(),
        user_text="me interesa, como puedo verla?",
        capture_data=capture,
        catalog_path="data/rent.csv",
    )
    assert phase == Phase.VISIT_INTAKE


def test_decide_phase_visit_confirm_when_answered() -> None:
    capture = mark_visit_pending(
        {},
        interest_text="me interesa",
        property_ref="Duplex",
    )
    capture = mark_visit_prompt_sent(capture)
    capture["visit_answered"] = True
    capture["visit_schedule_raw"] = "fin de semana, tarde"
    phase = decide_phase(
        "alquiler",
        profile=_complete_profile(),
        user_text="fin de semana, tarde",
        capture_data=capture,
        catalog_path="data/rent.csv",
    )
    assert phase == Phase.VISIT_CONFIRM


def test_visit_turn1_asks_schedule_without_lead() -> None:
    async def _run() -> None:
        with patch(
            "app.conversation_flow._resolve_listing_for_plan",
            new_callable=AsyncMock,
            side_effect=lambda ctx, user_text, plan: plan,
        ):
            result = await handle_turn(
                tenant_name="Espacios360",
                flow_path="alquiler",
                catalog_sale_path="data/sale.csv",
                catalog_rent_path="data/rent.csv",
                system_prompt_override=None,
                capture_data={
                    "intake_answered": True,
                    "search_criteria_llm": {
                        "property_types": ["departamento"],
                        "min_bedrooms": 2,
                        "any_zone": False,
                        "zone_tokens": ["centro"],
                    },
                    "last_listing": {
                        "ids": ["1"],
                        "branch": "alquiler",
                        "catalog_path": "data/rent.csv",
                    },
                },
                user_text="me interesa, como puedo verla?",
                session_flow_path="alquiler",
                phone_number_id="pnid",
                wa_id="54911",
            )
        assert result.phase == Phase.VISIT_INTAKE.value
        assert result.visit_lead_type is None
        assert not result.alerts
        assert get_visit_pending(result.capture_data)
        assert get_visit_prompt_sent(result.capture_data)
        assert "días" in result.text.lower() or "dias" in result.text.lower()
        assert "Registré tu interés" not in result.text

    asyncio.run(_run())


def test_visit_turn2_confirms_and_prepares_lead() -> None:
    async def _run() -> None:
        capture = mark_visit_pending(
            {
                "intake_answered": True,
                "search_criteria_llm": {
                    "property_types": ["departamento"],
                    "min_bedrooms": 2,
                    "any_zone": False,
                    "zone_tokens": ["centro"],
                },
                "last_listing": {
                    "ids": ["10"],
                    "branch": "alquiler",
                    "catalog_path": "data/rent.csv",
                },
                "last_viewed_property": {
                    "id": "10",
                    "catalog_path": "data/rent.csv",
                    "branch": "alquiler",
                },
            },
            interest_text="me interesa, como puedo verla?",
            property_ref="Duplex Chacabuco al 100",
        )
        capture = mark_visit_prompt_sent(capture)

        mock_summary = VisitLeadSummary(
            interest_summary="Interés en visitar Duplex Chacabuco",
            conversation_summary=(
                "Cliente busca alquiler en centro. Vio opciones y quiere visitar "
                "el duplex; prefiere fin de semana por la tarde."
            ),
        )

        with (
            patch(
                "app.conversation_flow._resolve_listing_for_plan",
                new_callable=AsyncMock,
                side_effect=lambda ctx, user_text, plan: plan,
            ),
            patch(
                "app.conversation_flow.summarize_visit_lead",
                new_callable=AsyncMock,
                return_value=mock_summary,
            ) as mock_summarize,
        ):
            result = await handle_turn(
                tenant_name="Espacios360",
                flow_path="alquiler",
                catalog_sale_path="data/sale.csv",
                catalog_rent_path="data/rent.csv",
                system_prompt_override=None,
                capture_data=capture,
                user_text="prefiero fin de semana por la tarde",
                session_flow_path="alquiler",
                phone_number_id="pnid",
                wa_id="54911",
                contact_name="Leo",
            )

        assert result.phase == Phase.VISIT_CONFIRM.value
        assert result.visit_lead_type == "alquiler"
        assert "fin de semana" in result.visit_lead_conversation_summary.lower()
        assert (
            result.visit_lead_conversation_summary
            != "prefiero fin de semana por la tarde"
        )
        assert "Registré tu interés" in result.text
        assert "preferencia general" not in result.text.lower()
        mock_summarize.assert_awaited_once()
        assert (
            mock_summarize.await_args.kwargs["visit_schedule_raw"]
            == "prefiero fin de semana por la tarde"
        )
        assert not get_visit_pending(result.capture_data)

    asyncio.run(_run())


def test_reset_visit_on_flow_switch() -> None:
    capture = mark_visit_pending({}, interest_text="visitar", property_ref="x")
    capture = reset_visit_state(capture)
    assert not get_visit_pending(capture)
    assert not is_visit_collecting(capture)
