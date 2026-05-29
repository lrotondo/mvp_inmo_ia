from __future__ import annotations

from app.capture_flow import (
    bot_offered_visit,
    clear_bot_offered_visit,
    merge_outbound_capture_flags,
)
from app.conversation_flow import _wants_visit

_CAPTURE_LISTING = {
    "last_listing": {
        "ids": ["10", "11", "12"],
        "catalog_path": "data/x.csv",
        "branch": "alquiler",
    },
    "focused_listing_option_index": 2,
}

_VISIT_OFFER_TEXT = (
    "En la ficha no se especifica si aceptan mascotas. "
    "¿Te interesa agendar una visita para conocerla?"
)


def test_merge_outbound_marks_visit_offer() -> None:
    merged = merge_outbound_capture_flags({}, _VISIT_OFFER_TEXT)
    assert bot_offered_visit(merged)


def test_merge_outbound_clears_offer_on_schedule_question() -> None:
    capture = merge_outbound_capture_flags({}, _VISIT_OFFER_TEXT)
    assert bot_offered_visit(capture)
    schedule = (
        "¡Genial! Para que un asesor te contacte y coordinen la visita de *Casa X*, "
        "contame en *un solo mensaje*:\n"
        "• ¿Qué *días* te vienen bien?"
    )
    merged = merge_outbound_capture_flags(capture, schedule)
    assert not bot_offered_visit(merged)


def test_wants_visit_short_affirm_after_bot_offer() -> None:
    capture = merge_outbound_capture_flags(dict(_CAPTURE_LISTING), _VISIT_OFFER_TEXT)
    assert _wants_visit(
        "alquiler",
        "si",
        capture,
        catalog_path="data/x.csv",
    )
    assert _wants_visit(
        "alquiler",
        "sí",
        capture,
        catalog_path="data/x.csv",
    )


def test_wants_visit_short_affirm_without_offer_is_false() -> None:
    assert not _wants_visit(
        "alquiler",
        "si",
        _CAPTURE_LISTING,
        catalog_path="data/x.csv",
    )


def test_wants_visit_short_affirm_without_listing_context_is_false() -> None:
    capture = merge_outbound_capture_flags({}, _VISIT_OFFER_TEXT)
    assert not _wants_visit("alquiler", "si", capture)


def test_clear_bot_offered_visit() -> None:
    capture = merge_outbound_capture_flags({}, _VISIT_OFFER_TEXT)
    cleared = clear_bot_offered_visit(capture)
    assert not bot_offered_visit(cleared)
