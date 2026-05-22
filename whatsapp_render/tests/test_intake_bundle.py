from __future__ import annotations

from app.conversation_flow import Phase, decide_phase
from app.prompts.templates import build_intake_bundle_question
from app.search_profile import (
    SearchProfile,
    build_search_profile,
    get_intake_answered,
    mark_intake_answered,
    mark_intake_prompt_sent,
    reset_intake_state,
)


def test_intake_bundle_questions_mention_fields() -> None:
    alq = build_intake_bundle_question("alquiler").lower()
    assert "casa" in alq and "departamento" in alq
    assert "dormitorio" in alq
    assert "zona" in alq

    compra = build_intake_bundle_question("compra").lower()
    assert "lote" in compra
    assert "presupuesto" in compra


def test_intake_not_complete_until_answered() -> None:
    capture = reset_intake_state({})
    profile = build_search_profile(capture, "centro 2 dorm", "alquiler")
    assert not profile.is_complete
    assert decide_phase("alquiler", profile=profile, user_text="hola", capture_data=capture, catalog_path="x") == Phase.INTAKE


def test_intake_complete_after_mark_answered() -> None:
    capture = mark_intake_prompt_sent(reset_intake_state({}))
    capture = mark_intake_answered(
        capture,
        "depto en centro 2 dormitorios",
        criteria_llm={
            "property_types": ["departamento"],
            "min_bedrooms": 2,
            "max_price_usd": None,
            "zone_tokens": ["centro"],
            "any_zone": False,
            "notes": "",
        },
    )
    assert get_intake_answered(capture)
    profile = build_search_profile(capture, "", "alquiler")
    assert profile.is_complete
    assert profile.property_types == ("departamento",)


def test_decide_waitlist_when_rejects_listing() -> None:
    profile = SearchProfile(
        branch="alquiler",
        property_type="departamento",
        property_types=("departamento",),
        intake_complete=True,
    )
    capture = {
        "intake_answered": True,
        "last_listing": {"ids": ["1"], "catalog_path": "data/x.csv"},
    }
    phase = decide_phase(
        "alquiler",
        profile=profile,
        user_text="ninguna me sirve",
        capture_data=capture,
        catalog_path="data/x.csv",
    )
    assert phase == Phase.WAITLIST
