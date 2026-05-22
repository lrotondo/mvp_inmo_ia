from app.capture_flow import append_user_flow_message
from app.catalog_search import parse_search_criteria
from app.search_profile import (
    build_search_profile,
    get_intake_answered,
    is_intake_complete,
    mark_intake_answered,
    mark_intake_prompt_sent,
    reset_intake_state,
)
from app.prompts.templates import build_intake_bundle_question


def test_zone_parse_centro_and_cerca_del_centro() -> None:
    criteria = parse_search_criteria(
        "departamento Cerca del centro",
        branch="alquiler",
    )
    assert "centro" in criteria.zone_tokens

    criteria2 = parse_search_criteria("Centro", branch="alquiler")
    assert "centro" in criteria2.zone_tokens


def test_intake_bundle_single_question() -> None:
    capture = reset_intake_state({})
    profile = build_search_profile(capture, "", "alquiler")
    assert not profile.is_complete
    q = profile.next_question() or ""
    assert "casa" in q.lower() and "dormitorio" in q.lower()
    assert q == build_intake_bundle_question("alquiler")


def test_intake_complete_after_single_answer() -> None:
    capture = mark_intake_prompt_sent(reset_intake_state({}))
    capture = mark_intake_answered(
        capture,
        "departamento cerca del centro 2 dormitorios",
        criteria_llm={
            "property_types": ["departamento"],
            "min_bedrooms": 2,
            "max_price_usd": None,
            "zone_tokens": ["centro"],
            "any_zone": False,
            "notes": "",
        },
    )
    final = build_search_profile(capture, "", "alquiler")
    assert final.is_complete
    assert final.property_type == "departamento"
    assert final.min_bedrooms >= 2
    assert "centro" in final.zone_tokens


def test_early_listing_on_browse_phrase() -> None:
    capture = mark_intake_answered(
        mark_intake_prompt_sent({}),
        "casa 2 dorm sin preferencia de zona",
        criteria_llm={
            "property_types": ["casa"],
            "min_bedrooms": 2,
            "any_zone": True,
            "zone_tokens": [],
            "max_price_usd": None,
            "notes": "",
        },
    )
    capture = append_user_flow_message(capture, "alquiler", "mostrame opciones")
    profile = build_search_profile(capture, "mostrame opciones", "alquiler")
    assert profile.is_complete


def test_compra_intake_single_bundle_then_answer() -> None:
    capture = mark_intake_answered(
        mark_intake_prompt_sent({}),
        "casa en centro 3 dormitorios usd 80000",
        criteria_llm={
            "property_types": ["casa"],
            "min_bedrooms": 3,
            "max_price_usd": 80000,
            "zone_tokens": ["centro"],
            "any_zone": False,
            "notes": "",
        },
    )
    assert get_intake_answered(capture)
    assert is_intake_complete(capture)
    final = build_search_profile(capture, "", "compra")
    assert final.is_complete
    assert final.property_type == "casa"
    assert final.max_price_usd == 80000
