from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.conversation_flow import Phase, decide_phase, handle_turn
from app.listing_context import user_requests_more_listing_only
from app.prompts.templates import format_visit_confirmation
from app.search_profile import SearchProfile
from app.session_lifecycle import mark_advisor_handoff_completed
from app.visit_flow import (
    user_declines_visit,
    visit_schedule_message_is_substantive,
)
from app.visit_intent import visit_requests_human_only

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"

_CAPTURE_VISIT_SCHEDULE = {
    "intake_answered": True,
    "intake_prompt_sent": True,
    "visit_pending": True,
    "visit_prompt_sent": True,
    "visit_answered": False,
    "visit_interest_text": "quiero hablar con un asesor",
    "visit_property_ref": "Casa de dos dormitorios con patio",
    "last_listing": {
        "ids": ["10", "11", "12"],
        "branch": "alquiler",
        "catalog_path": TENANT_RENT,
    },
    "shown_listing_ids": ["10", "11", "12"],
    "search_profile": {
        "branch": "alquiler",
        "property_types": ["casa"],
        "intake_complete": True,
        "missing_fields": [],
    },
}


def _complete_profile() -> SearchProfile:
    return SearchProfile(
        branch="alquiler",
        property_types=("casa",),
        any_zone=True,
        intake_complete=True,
    )


def test_user_declines_visit_no_no_quiero() -> None:
    assert user_declines_visit("no, no quiero")


def test_user_requests_more_listing_quiero_ver_mas() -> None:
    assert user_requests_more_listing_only("quiero ver mas opciones")


def test_visit_schedule_substantive_days() -> None:
    assert visit_schedule_message_is_substantive("martes y jueves por la tarde")
    assert visit_schedule_message_is_substantive("sin horario")


def test_visit_schedule_not_substantive_on_decline() -> None:
    assert not visit_schedule_message_is_substantive("no, no quiero")


def test_visit_requests_human_only() -> None:
    assert visit_requests_human_only("quiero hablar con un asesor", "alquiler")
    assert not visit_requests_human_only("quiero visitar la casa", "alquiler")


def test_decide_phase_decline_is_general_not_confirm() -> None:
    phase = decide_phase(
        "alquiler",
        profile=_complete_profile(),
        user_text="no, no quiero",
        capture_data=_CAPTURE_VISIT_SCHEDULE,
        catalog_path=TENANT_RENT,
    )
    assert phase == Phase.GENERAL
    assert phase != Phase.VISIT_CONFIRM


def test_decide_phase_more_options_is_listing() -> None:
    phase = decide_phase(
        "alquiler",
        profile=_complete_profile(),
        user_text="quiero ver mas opciones",
        capture_data=_CAPTURE_VISIT_SCHEDULE,
        catalog_path=TENANT_RENT,
    )
    assert phase == Phase.LISTING


def test_handle_turn_decline_does_not_confirm_visit() -> None:
    async def _run():
        with (
            patch(
                "app.conversation_flow.chat_completion",
                new_callable=AsyncMock,
                return_value="ok",
            ),
            patch(
                "app.conversation_flow.summarize_visit_lead",
                new_callable=AsyncMock,
            ) as mock_lead,
        ):
            result = await handle_turn(
                tenant_name="Cowork",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                system_prompt_override=None,
                capture_data=dict(_CAPTURE_VISIT_SCHEDULE),
                user_text="no, no quiero",
                session_flow_path="alquiler",
            )
        mock_lead.assert_not_called()
        assert result.phase != Phase.VISIT_CONFIRM.value
        assert "Registré tu interés" not in result.text
        assert not result.capture_data.get("visit_pending")
        assert "Sin problema" in result.text

    asyncio.run(_run())


def test_handle_turn_more_options_not_confirm_visit() -> None:
    fake_pick = type("R", (), {"ids": ["20", "21"], "rows": [], "empty_reason": ""})()

    async def _run():
        with (
            patch(
                "app.conversation_flow.pick_listing_properties",
                new_callable=AsyncMock,
                return_value=fake_pick,
            ),
            patch(
                "app.conversation_flow.summarize_visit_lead",
                new_callable=AsyncMock,
            ) as mock_lead,
        ):
            result = await handle_turn(
                tenant_name="Cowork",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                system_prompt_override=None,
                capture_data=dict(_CAPTURE_VISIT_SCHEDULE),
                user_text="quiero ver mas opciones",
                session_flow_path="alquiler",
            )
        mock_lead.assert_not_called()
        assert result.phase != Phase.VISIT_CONFIRM.value
        assert "Registré tu interés" not in result.text
        assert not result.capture_data.get("visit_pending")
        assert "Entendido" in result.text

    asyncio.run(_run())


def test_handle_turn_substantive_schedule_confirms_visit() -> None:
    from app.visit_lead import VisitLeadSummary

    summary = VisitLeadSummary(
        interest_summary="Interés en casa",
        conversation_summary="Cliente disponible martes y jueves por la tarde.",
    )

    async def _run():
        with patch(
            "app.conversation_flow.summarize_visit_lead",
            new_callable=AsyncMock,
            return_value=summary,
        ) as mock_lead:
            result = await handle_turn(
                tenant_name="Cowork",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                system_prompt_override=None,
                capture_data=dict(_CAPTURE_VISIT_SCHEDULE),
                user_text="martes y jueves por la tarde",
                session_flow_path="alquiler",
            )
        mock_lead.assert_awaited_once()
        assert result.phase == Phase.VISIT_CONFIRM.value
        assert "Registré tu interés" in result.text
        assert result.capture_data.get("advisor_handoff_completed_at")

    asyncio.run(_run())


def test_handle_turn_human_only_skips_schedule_question() -> None:
    from app.visit_lead import VisitLeadSummary

    capture = {
        "intake_answered": True,
        "last_listing": {
            "ids": ["10"],
            "branch": "alquiler",
            "catalog_path": TENANT_RENT,
        },
        "last_viewed_property": {
            "id": "10",
            "catalog_path": TENANT_RENT,
            "branch": "alquiler",
        },
        "search_profile": _CAPTURE_VISIT_SCHEDULE["search_profile"],
    }
    summary = VisitLeadSummary(
        interest_summary="Contacto con asesor",
        conversation_summary="Cliente pidió hablar con un asesor.",
    )

    async def _run():
        with patch(
            "app.conversation_flow.summarize_visit_lead",
            new_callable=AsyncMock,
            return_value=summary,
        ):
            result = await handle_turn(
                tenant_name="Cowork",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                system_prompt_override=None,
                capture_data=capture,
                user_text="quiero hablar con un asesor",
                session_flow_path="alquiler",
            )
        assert result.phase == Phase.VISIT_CONFIRM.value
        assert "días" not in result.text.lower() or "Registré tu interés" in result.text
        assert "Registré tu interés" in result.text

    asyncio.run(_run())


def test_handle_turn_no_duplicate_visit_confirm_after_handoff() -> None:
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    capture = mark_advisor_handoff_completed(
        {
            **_CAPTURE_VISIT_SCHEDULE,
            "visit_answered": True,
            "visit_schedule_raw": "martes tarde",
        },
        handoff_kind="visit",
        context_ref="Casa X",
        now=now,
    )

    async def _run():
        with (
            patch(
                "app.conversation_flow.summarize_visit_lead",
                new_callable=AsyncMock,
            ) as mock_lead,
            patch(
                "app.conversation_flow.handle_post_handoff_turn",
                new_callable=AsyncMock,
                return_value=(
                    "Seguimos buscando.",
                    capture,
                    "post_handoff_new_search",
                    False,
                    True,
                    None,
                ),
            ),
        ):
            result = await handle_turn(
                tenant_name="Cowork",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                system_prompt_override=None,
                capture_data=capture,
                user_text="quiero ver mas opciones",
                session_flow_path="alquiler",
            )
        mock_lead.assert_not_called()
        assert result.text != format_visit_confirmation("Casa X")
        assert "Registré tu interés" not in result.text

    asyncio.run(_run())
