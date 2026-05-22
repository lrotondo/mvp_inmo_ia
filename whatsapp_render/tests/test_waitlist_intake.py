from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.conversation_flow import Phase, decide_phase
from app.prompts.templates import build_waitlist_bundle_question
from app.waitlist_flow import (
    get_waitlist_answered,
    get_waitlist_pending,
    get_waitlist_raw_text,
    mark_waitlist_answered,
    mark_waitlist_pending,
    mark_waitlist_prompt_sent,
)
from app.waitlist import summarize_waitlist_requirements
from app.search_profile import SearchProfile


def _complete_profile() -> SearchProfile:
    return SearchProfile(
        branch="alquiler",
        property_type="departamento",
        property_types=("departamento",),
        min_bedrooms=2,
        any_zone=True,
        intake_complete=True,
    )


def test_waitlist_bundle_question_mentions_requirements() -> None:
    text = build_waitlist_bundle_question("alquiler").lower()
    assert "lista de espera" in text
    assert "dormitorio" in text
    assert "zona" in text


def test_reject_does_not_set_raw_text_on_first_turn() -> None:
    capture = mark_waitlist_pending(
        {"last_listing": {"ids": ["1"], "catalog_path": "x"}}
    )
    phase = decide_phase(
        "alquiler",
        profile=_complete_profile(),
        user_text="no me sirve ninguna",
        capture_data=capture,
        catalog_path="x",
    )
    assert phase == Phase.WAITLIST_INTAKE
    assert not get_waitlist_answered(capture)
    assert get_waitlist_raw_text(capture) == ""


def test_answer_turn_sets_confirm_phase() -> None:
    capture = mark_waitlist_answered(
        mark_waitlist_prompt_sent(
            mark_waitlist_pending(
                {"last_listing": {"ids": ["1"], "catalog_path": "x"}}
            )
        ),
        "casa 3 dorm en centro hasta 200000 usd con patio",
    )
    phase = decide_phase(
        "compra",
        profile=_complete_profile(),
        user_text="casa 3 dorm en centro hasta 200000 usd con patio",
        capture_data=capture,
        catalog_path="x",
    )
    assert phase == Phase.WAITLIST_CONFIRM
    assert "patio" in get_waitlist_raw_text(capture)


def test_summarize_uses_waitlist_raw_text() -> None:
    async def _run():
        mock_json = (
            '{"zona":"Centro","presupuesto":"USD 200000","ambientes":"3",'
            '"preferencias":"patio","notas":"","requirements_summary":'
            '"Busca casa 3 dorm en centro con patio hasta 200k.",'
            '"conversation_summary":"Cliente en compra, rechazó listado."}'
        )
        with patch(
            "app.waitlist.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_json,
        ):
            return await summarize_waitlist_requirements(
                seek_type="compra",
                waitlist_raw_text="casa 3 dorm centro patio 200000 usd",
                intake_text="casa centro",
            )

    result = asyncio.run(_run())
    assert "Centro" in result.zona or "centro" in result.requirements_summary.lower()
    assert "patio" in result.preferencias.lower() or "patio" in result.requirements_summary.lower()
