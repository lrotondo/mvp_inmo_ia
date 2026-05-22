from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.llm.intake_extraction import criteria_from_fallback_text, extract_search_criteria
from app.llm.listing_picker import pick_listing_properties
from app.search_profile import SearchProfile


def test_extract_search_criteria_fallback_without_api() -> None:
    async def _run():
        with patch("app.llm.intake_extraction.chat_completion", new_callable=AsyncMock) as mock:
            mock.side_effect = RuntimeError("no key")
            return await extract_search_criteria(
                "casa en centro 3 dormitorios usd 200000",
                branch="compra",
            )

    result = asyncio.run(_run())
    assert "casa" in result.property_types
    assert result.min_bedrooms >= 2


def test_criteria_from_fallback_text() -> None:
    c = criteria_from_fallback_text("departamento 2 dorm sin preferencia de zona", "alquiler")
    assert "departamento" in c.property_types
    assert c.any_zone


def test_picker_validates_ids() -> None:
    rows = [
        {
            "ID": "A1",
            "Tipo": "Casa",
            "Titulo": "Casa 1",
            "Precio": "US$ 50.000",
            "Disponible": "si",
            "Dormitorios": "2",
        },
        {
            "ID": "A2",
            "Tipo": "Casa",
            "Titulo": "Casa 2",
            "Precio": "US$ 60.000",
            "Disponible": "si",
            "Dormitorios": "3",
        },
        {
            "ID": "A3",
            "Tipo": "Casa",
            "Titulo": "Casa 3",
            "Precio": "US$ 70.000",
            "Disponible": "si",
            "Dormitorios": "2",
        },
    ]
    profile = SearchProfile(
        branch="compra",
        property_type="casa",
        property_types=("casa",),
        min_bedrooms=2,
        max_price_usd=100_000,
        any_zone=True,
        intake_complete=True,
    )
    mock_response = '{"ids": ["FAKE", "A2", "A1"], "empty_reason": ""}'

    async def _run():
        with patch("app.llm.listing_picker.chat_completion", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            return await pick_listing_properties(
                rows,
                profile,
                "casa 2 dorm",
                branch="compra",
                exclude_ids=["A1"],
                mode="more_options",
            )

    result = asyncio.run(_run())
    assert "FAKE" not in result.ids
    assert "A1" not in result.ids
    assert result.ids == ["A2"]
