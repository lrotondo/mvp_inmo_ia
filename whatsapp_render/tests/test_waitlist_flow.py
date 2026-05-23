from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.conversation_flow import Phase, decide_phase
from app.listing_context import (
    user_rejects_all_listings,
    user_requests_new_search,
    user_wants_alternate_listing,
)
from app.search_profile import SearchProfile, is_intake_complete
from app.waitlist_flow import (
    user_affirms_waitlist_consent,
    waitlist_message_is_substantive,
)

TENANT_SALE = "data/tenants/inmobiliaria_cowork.csv"


def test_user_rejects_no_ninguna() -> None:
    assert user_rejects_all_listings("no, ninguna. necesito una casa con pileta")
    assert user_wants_alternate_listing("no, ninguna")


def test_user_affirms_waitlist_consent() -> None:
    assert user_affirms_waitlist_consent("si")
    assert user_affirms_waitlist_consent("Sí!")
    assert not user_affirms_waitlist_consent("busco casas de 2 dormitorios")


def test_waitlist_substantive_message() -> None:
    text = "busco casas de 2 dormitorios o mas, en cualquier zona con pileta"
    assert waitlist_message_is_substantive(text)


def test_new_search_false_with_requirements_hint() -> None:
    capture = {"intake_answered": True}
    text = "busco casas de 2 dormitorios o mas, en cualquier zona con pileta"
    assert not user_requests_new_search(text, capture)


def test_decide_phase_reject_goes_listing_not_waitlist() -> None:
    profile = SearchProfile(
        branch="compra",
        property_types=("casa",),
        min_bedrooms=2,
        any_zone=True,
        intake_complete=True,
    )
    capture = {
        "intake_answered": True,
        "last_listing": {"ids": ["1"], "branch": "compra", "catalog_path": TENANT_SALE},
    }
    phase = decide_phase(
        "compra",
        profile=profile,
        user_text="no, ninguna",
        capture_data=capture,
        catalog_path=TENANT_SALE,
    )
    assert phase == Phase.LISTING


def test_decide_phase_waitlist_consent_when_pending() -> None:
    capture = {"waitlist_pending": True, "waitlist_consent_sent": False}
    profile = SearchProfile(branch="compra", intake_complete=True)
    phase = decide_phase(
        "compra",
        profile=profile,
        user_text="",
        capture_data=capture,
        catalog_path=TENANT_SALE,
    )
    assert phase == Phase.WAITLIST_CONSENT


def test_decide_phase_waitlist_intake_after_si() -> None:
    capture = {
        "waitlist_pending": True,
        "waitlist_consent_sent": True,
        "waitlist_prompt_sent": False,
    }
    profile = SearchProfile(branch="compra", intake_complete=True)
    phase = decide_phase(
        "compra",
        profile=profile,
        user_text="si",
        capture_data=capture,
        catalog_path=TENANT_SALE,
    )
    assert phase == Phase.WAITLIST_INTAKE


def test_handle_turn_reject_empty_catalog_starts_waitlist_consent() -> None:
    import asyncio
    from app.conversation_flow import handle_turn

    capture = {
        "intake_answered": True,
        "search_criteria_llm": {
            "property_types": ["casa"],
            "min_bedrooms": 2,
            "any_zone": True,
        },
        "last_listing": {"ids": ["1"], "branch": "compra", "catalog_path": TENANT_SALE},
        "shown_listing_ids": ["1"],
    }
    empty_pick = type("R", (), {"ids": [], "rows": [], "empty_reason": "empty"})()

    async def _run():
        with patch(
            "app.conversation_flow.pick_listing_properties",
            new_callable=AsyncMock,
            return_value=empty_pick,
        ):
            return await handle_turn(
                tenant_name="Test",
                flow_path="compra",
                catalog_sale_path=TENANT_SALE,
                catalog_rent_path=None,
                system_prompt_override=None,
                capture_data=capture,
                user_text="no, ninguna",
                session_flow_path="compra",
            )

    result = asyncio.run(_run())
    assert result.phase == Phase.WAITLIST_CONSENT.value
    assert "datos" in result.text.lower() or "asesor" in result.text.lower()
    assert result.capture_data.get("waitlist_pending")
    assert result.skip_property_delivery


def test_intake_complete_not_reset_on_requirements_busco() -> None:
    capture = {"intake_answered": True, "intake_prompt_sent": True}
    assert is_intake_complete(
        capture,
        current_user_text="busco casas de 2 dormitorios con pileta en cualquier zona",
    )
