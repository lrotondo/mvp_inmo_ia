from app.capture_flow import append_user_flow_message
from app.catalog_search import parse_search_criteria
from app.search_profile import (
    build_search_profile,
    bump_intake_step,
    get_intake_step,
    is_intake_script_done,
)


def test_zone_parse_centro_and_cerca_del_centro() -> None:
    criteria = parse_search_criteria(
        "departamento Cerca del centro",
        branch="alquiler",
    )
    assert "centro" in criteria.zone_tokens

    criteria2 = parse_search_criteria("Centro", branch="alquiler")
    assert "centro" in criteria2.zone_tokens


def test_intake_advances_without_validating_zone() -> None:
    capture: dict = {"intake_step": 0}
    for user_msg, expect_field in (
        ("quiero alquilar", "casa"),
        ("Departamento", "zona"),
        ("Cerca del centro", "dormitorio"),
    ):
        profile = build_search_profile(capture, user_msg, "alquiler")
        assert not profile.is_complete
        q = (profile.next_question() or "").lower()
        assert expect_field in q
        capture = bump_intake_step(
            append_user_flow_message(capture, "alquiler", user_msg),
            "alquiler",
        )

    profile = build_search_profile(capture, "2", "alquiler")
    capture = bump_intake_step(
        append_user_flow_message(capture, "alquiler", "2"),
        "alquiler",
    )
    final = build_search_profile(capture, "", "alquiler")
    assert final.is_complete
    assert final.property_type == "departamento"
    assert final.min_bedrooms >= 2
    assert "centro" in final.zone_tokens


def test_early_listing_on_browse_phrase() -> None:
    capture = append_user_flow_message({}, "alquiler", "quiero alquilar")
    profile = build_search_profile(capture, "mostrame opciones", "alquiler")
    assert profile.is_complete


def test_compra_intake_four_steps() -> None:
    capture: dict = {}
    for msg in ("busco comprar", "casa", "centro", "3 dormitorios"):
        profile = build_search_profile(capture, msg, "compra")
        capture = bump_intake_step(
            append_user_flow_message(capture, "compra", msg),
            "compra",
        )
    profile = build_search_profile(capture, "usd 80000", "compra")
    capture = bump_intake_step(
        append_user_flow_message(capture, "compra", "usd 80000"),
        "compra",
    )
    assert get_intake_step(capture) >= 4
    assert is_intake_script_done(capture, "compra")
    final = build_search_profile(capture, "", "compra")
    assert final.is_complete
    assert final.property_type == "casa"
    assert final.max_price_usd == 80000
