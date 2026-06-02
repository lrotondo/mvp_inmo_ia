from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.llm.institutional_classifier import (
    InstitutionalCategory,
    classify_institutional_fallback,
    classify_institutional_message,
)


def test_fallback_office_hours() -> None:
    assert (
        classify_institutional_fallback("¿qué horario tienen?")
        == InstitutionalCategory.OFFICE_HOURS
    )


def test_fallback_office_location() -> None:
    assert (
        classify_institutional_fallback("¿dónde queda la inmobiliaria?")
        == InstitutionalCategory.OFFICE_LOCATION
    )


def test_fallback_social_links() -> None:
    assert (
        classify_institutional_fallback("tienen instagram?")
        == InstitutionalCategory.SOCIAL_LINKS
    )


def test_fallback_none_for_property_search() -> None:
    assert (
        classify_institutional_fallback("quiero ver mas opciones")
        == InstitutionalCategory.NONE
    )


def test_llm_classify_office_hours() -> None:
    async def _run() -> None:
        with patch(
            "app.llm.institutional_classifier.chat_completion",
            new_callable=AsyncMock,
            return_value='{"category": "office_hours"}',
        ):
            cat = await classify_institutional_message(
                user_text="¿a qué hora atienden?",
                flow_path="alquiler",
            )
        assert cat == InstitutionalCategory.OFFICE_HOURS

    asyncio.run(_run())
