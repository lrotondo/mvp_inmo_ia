from __future__ import annotations

from app.listing_context import (
    listing_already_shown,
    user_asks_about_shown_listing,
    user_requests_fresh_listing,
)
from app.turn_handler import TurnKind, resolve_turn_kind
from app.visit_intent import conversation_wants_visit_rent
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


def test_followup_not_listing_after_last_listing_in_capture() -> None:
    capture = {"last_listing": {"ids": ["1", "2", "3"], "catalog_path": "data/x.csv"}}
    kind = resolve_turn_kind(
        "alquiler",
        profile=_complete_profile(),
        current_user_text="la opción 2 tiene pileta?",
        capture_data=capture,
        catalog_path_used="data/x.csv",
    )
    assert kind == TurnKind.GENERAL


def test_option_number_alone_is_detail_not_general() -> None:
    capture = {"last_listing": {"ids": ["6", "5", "2"], "catalog_path": "x"}}
    kind = resolve_turn_kind(
        "alquiler",
        profile=_complete_profile(),
        current_user_text="la opcion 2",
        capture_data=capture,
        catalog_path_used="x",
    )
    assert kind == TurnKind.DETAIL


def test_reject_all_goes_waitlist_intake() -> None:
    capture = {"last_listing": {"ids": ["1", "2", "3"], "catalog_path": "x"}}
    kind = resolve_turn_kind(
        "alquiler",
        profile=_complete_profile(),
        current_user_text="ninguna de estas me sirve",
        capture_data=capture,
        catalog_path_used="x",
    )
    assert kind == TurnKind.WAITLIST_INTAKE


def test_waitlist_answered_goes_confirm() -> None:
    capture = {
        "last_listing": {"ids": ["1"], "catalog_path": "x"},
        "waitlist_pending": True,
        "waitlist_prompt_sent": True,
        "waitlist_answered": True,
        "waitlist_raw_text": "depto 2 dorm centro hasta 300000",
    }
    kind = resolve_turn_kind(
        "compra",
        profile=_complete_profile(),
        current_user_text="depto 2 dorm centro hasta 300000",
        capture_data=capture,
        catalog_path_used="x",
    )
    assert kind == TurnKind.WAITLIST_CONFIRM


def test_fresh_listing_request_stays_listing() -> None:
    capture = {"last_listing": {"ids": ["1", "2", "3"], "catalog_path": "x"}}
    kind = resolve_turn_kind(
        "alquiler",
        profile=_complete_profile(),
        current_user_text="mostrame otras opciones",
        capture_data=capture,
        catalog_path_used="x",
    )
    assert kind == TurnKind.LISTING


def test_alquiler_verlos_detected_as_visit_intent() -> None:
    assert conversation_wants_visit_rent("Cuando podría verlos?")


def test_listing_helpers() -> None:
    assert user_asks_about_shown_listing("cuántos metros tiene la segunda?")
    assert user_requests_fresh_listing("qué tenés disponible?")
    assert listing_already_shown(
        catalog_csv_path=None,
        capture_data={"last_listing": {"ids": ["1"], "catalog_path": "p"}},
    )
