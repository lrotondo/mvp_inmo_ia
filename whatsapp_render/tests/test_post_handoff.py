from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.conversation_flow import handle_turn
from app.llm.post_handoff_classifier import (
    PostHandoffCategory,
    classify_post_handoff_fallback,
    classify_post_handoff_message,
)
from app.post_handoff import build_handoff_context_block
from app.session_lifecycle import mark_advisor_handoff_completed

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"

FAKE_ROW = {
    "ID": "8",
    "Titulo": "Departamento en primer piso ubicado al frente",
    "Direccion": "Saavedra al 700",
    "Barrio": "Centro",
    "Precio": "380000",
    "Dormitorios": "2",
    "Ambientes": "3",
    "Caracteristicas": "Living comedor, cocina separada",
}


def _visit_handoff_capture() -> dict:
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    capture = mark_advisor_handoff_completed(
        {
            "last_viewed_property": {
                "id": "8",
                "catalog_path": TENANT_RENT,
                "branch": "alquiler",
            },
            "intake_answered": True,
        },
        handoff_kind="visit",
        context_ref="Departamento en primer piso ubicado al frente",
        now=now,
    )
    return capture


def test_classify_fallback_thanks() -> None:
    assert (
        classify_post_handoff_fallback("gracias!")
        == PostHandoffCategory.THANKS
    )
    assert classify_post_handoff_fallback("ok") == PostHandoffCategory.THANKS


def test_classify_fallback_property_question() -> None:
    assert (
        classify_post_handoff_fallback("¿tiene cochera?")
        == PostHandoffCategory.PROPERTY_QUESTION
    )


def test_classify_fallback_new_search() -> None:
    assert (
        classify_post_handoff_fallback("quiero ver otras opciones")
        == PostHandoffCategory.NEW_SEARCH
    )


def test_classify_llm_thanks() -> None:
    async def _run() -> None:
        with patch(
            "app.llm.post_handoff_classifier.chat_completion",
            new_callable=AsyncMock,
            return_value='{"category": "thanks"}',
        ):
            cat = await classify_post_handoff_message(
                user_text="muchas gracias",
                handoff_kind="visit",
                context_ref="Depto Centro",
                property_context_block="Precio: 380000",
                flow_path="alquiler",
            )
        assert cat == PostHandoffCategory.THANKS

    asyncio.run(_run())


def test_build_handoff_context_visit() -> None:
    capture = _visit_handoff_capture()
    with patch(
        "app.post_handoff.load_last_viewed_property_row",
        return_value=FAKE_ROW,
    ):
        block = build_handoff_context_block(
            capture,
            handoff_kind="visit",
            catalog_path=TENANT_RENT,
            flow_path="alquiler",
        )
    assert "Saavedra" in block or "Centro" in block


def test_handle_turn_post_handoff_thanks_skips_outbound() -> None:
    async def _run() -> None:
        with patch(
            "app.conversation_flow.handle_post_handoff_turn",
            new_callable=AsyncMock,
            return_value=("", _visit_handoff_capture(), "post_handoff_thanks", True, True, None),
        ):
            result = await handle_turn(
                tenant_name="Cowork",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                system_prompt_override=None,
                capture_data=_visit_handoff_capture(),
                user_text="gracias",
                session_flow_path="alquiler",
            )
        assert result.skip_outbound is True
        assert result.text == ""
        assert result.phase == "post_handoff_thanks"

    asyncio.run(_run())


def test_handle_turn_post_handoff_property_question() -> None:
    async def _run() -> None:
        with patch(
            "app.conversation_flow.handle_post_handoff_turn",
            new_callable=AsyncMock,
            return_value=(
                "Sí, tiene living comedor según la ficha.",
                _visit_handoff_capture(),
                "post_handoff_property_question",
                False,
                True,
                None,
            ),
        ):
            result = await handle_turn(
                tenant_name="Cowork",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                system_prompt_override=None,
                capture_data=_visit_handoff_capture(),
                user_text="¿tiene living comedor?",
                session_flow_path="alquiler",
            )
        assert not result.skip_outbound
        assert "living comedor" in result.text.lower()
        assert "[LISTADO:" not in result.text

    asyncio.run(_run())


def test_handle_turn_post_handoff_new_search_restarts() -> None:
    async def _run() -> None:
        with patch(
            "app.conversation_flow.handle_post_handoff_turn",
            new_callable=AsyncMock,
            return_value=(
                "¿Querés comprar, alquilar o vender?",
                {},
                "post_handoff_new_search",
                False,
                True,
                "nuevo",
            ),
        ):
            result = await handle_turn(
                tenant_name="Cowork",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                system_prompt_override=None,
                capture_data=_visit_handoff_capture(),
                user_text="quiero buscar otra cosa",
                session_flow_path="alquiler",
            )
        assert result.flow_path_override == "nuevo"
        assert "advisor_handoff_completed_at" not in result.capture_data
        assert result.phase == "post_handoff_new_search"

    asyncio.run(_run())


def test_mark_handoff_stores_kind_and_ref() -> None:
    capture = mark_advisor_handoff_completed(
        {},
        handoff_kind="visit",
        context_ref="Depto Centro",
    )
    assert capture.get("handoff_kind") == "visit"
    assert capture.get("handoff_context_ref") == "Depto Centro"
