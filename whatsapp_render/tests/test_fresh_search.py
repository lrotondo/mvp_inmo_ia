from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.conversation_flow import Phase, decide_phase
from app.detail_media import should_deliver_property_detail_ficha
from app.listing_context import (
    user_requests_fresh_listing,
    user_requests_more_listing_only,
    user_requests_new_search,
)
from app.listing_delivery import deliver_bot_response
from app.prompts.templates import build_intake_bundle_question
from app.search_profile import (
    build_search_profile,
    is_intake_complete,
    reset_search_state,
    user_changes_property_type,
)

TENANT_SALE = "data/tenants/inmobiliaria_cowork.csv"

FAKE_ROW = {
    "ID": "8",
    "Titulo": "Departamento San Martin",
    "Direccion": "San Martin al 400",
    "Barrio": "Centro",
    "Caracteristicas": "Living comedor",
}


def test_user_requests_new_search_busquemos_casas() -> None:
    assert user_requests_new_search("busquemos casas en venta")
    assert user_requests_fresh_listing("busquemos casas en venta")


def test_user_requests_more_listing_without_reset() -> None:
    assert user_requests_fresh_listing("más opciones")
    assert user_requests_more_listing_only("más opciones")
    assert not user_requests_new_search("más opciones")


def test_is_intake_complete_false_on_new_search() -> None:
    capture = {"intake_answered": True}
    assert not is_intake_complete(
        capture,
        current_user_text="busquemos casas en venta",
    )


def test_user_changes_property_type_lote_to_casa() -> None:
    capture = {
        "search_profile": {
            "branch": "compra",
            "property_types": ["lote"],
            "intake_complete": True,
            "missing_fields": [],
        }
    }
    assert user_changes_property_type(
        "prefiero casas",
        capture,
        flow_path="compra",
    )


def test_reset_search_state_clears_listing_and_intake() -> None:
    capture = {
        "intake_answered": True,
        "intake_prompt_sent": True,
        "last_listing": {"ids": ["1"], "branch": "compra"},
        "shown_listing_ids": ["1"],
        "last_viewed_property": {"id": "8", "branch": "compra"},
        "search_profile": {"branch": "compra"},
        "visit_pending": True,
    }
    reset = reset_search_state(capture, flow_path="compra")
    assert not reset.get("intake_answered")
    assert "last_listing" not in reset
    assert "last_viewed_property" not in reset
    assert "search_profile" not in reset
    assert not reset.get("visit_pending")


def test_decide_phase_intake_after_new_search_reset() -> None:
    capture = reset_search_state(
        {
            "intake_answered": True,
            "last_listing": {"ids": ["1"], "branch": "compra", "catalog_path": TENANT_SALE},
            "last_viewed_property": {"id": "8", "catalog_path": TENANT_SALE, "branch": "compra"},
            "search_criteria_llm": {"property_types": ["lote"]},
        },
        flow_path="compra",
    )
    user_text = "busquemos casas en venta"
    profile = build_search_profile(capture, user_text, "compra")
    phase = decide_phase(
        "compra",
        profile=profile,
        user_text=user_text,
        capture_data=capture,
        catalog_path=TENANT_SALE,
    )
    assert phase == Phase.INTAKE
    assert not profile.is_complete


def test_should_not_deliver_ficha_on_new_search() -> None:
    message = build_intake_bundle_question("compra")
    assert not should_deliver_property_detail_ficha(
        flow_path="compra",
        property_ref="8",
        row=FAKE_ROW,
        outbound_message=message,
        current_user_text="busquemos casas en venta",
        capture_data={"intake_answered": True},
    )


def test_deliver_intake_bundle_without_visual() -> None:
    message = build_intake_bundle_question("compra")

    async def _run() -> None:
        with (
            patch(
                "app.listing_delivery.try_deliver_single_property_visual",
                new_callable=AsyncMock,
            ) as mock_visual,
            patch(
                "app.listing_delivery.send_whatsapp_text_message",
                new_callable=AsyncMock,
            ) as mock_text,
            patch(
                "app.listing_delivery.send_whatsapp_image_message",
                new_callable=AsyncMock,
            ) as mock_image,
        ):
            result = await deliver_bot_response(
                access_token="tok",
                phone_number_id="pnid",
                to_wa_id="54911",
                message=message,
                catalog_csv_path=TENANT_SALE,
                current_user_text="busquemos casas en venta",
                flow_path="compra",
                property_ref="8",
                skip_property_delivery=True,
            )
            assert "casa" in result.text.lower() or "departamento" in result.text.lower()
            mock_visual.assert_not_called()
            mock_image.assert_not_called()
            mock_text.assert_awaited_once()

    asyncio.run(_run())
