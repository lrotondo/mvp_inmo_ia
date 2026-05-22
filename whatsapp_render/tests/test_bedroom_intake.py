from __future__ import annotations

from app.bedroom_intake import bedroom_signal_in_text, parse_bedroom_count
from app.capture_flow import append_user_flow_message
from app.search_profile import build_search_profile


def test_parse_bare_range_2_o_3() -> None:
    assert parse_bedroom_count("2 ó 3") == 2
    assert bedroom_signal_in_text("2 ó 3") is True


def test_parse_single_digit_with_context() -> None:
    assert parse_bedroom_count("2 dormitorios") == 2


def test_search_profile_complete_after_bare_range() -> None:
    capture = append_user_flow_message(
        {},
        "alquiler",
        "departamento en alquiler",
    )
    capture = append_user_flow_message(
        capture, "alquiler", "sin preferencia de zona"
    )
    profile = build_search_profile(capture, "2 ó 3", "alquiler")
    assert "dormitorios" not in profile.missing_fields
    assert profile.min_bedrooms == 2
