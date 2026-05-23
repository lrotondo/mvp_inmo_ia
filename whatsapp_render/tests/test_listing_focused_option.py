from __future__ import annotations

from app.conversation import build_user_message_for_llm
from app.listing_context import (
    clear_focused_listing_option,
    get_focused_listing_option_index,
    merge_last_listing_into_capture,
    property_ref_from_listing_choice,
    resolve_listing_choice_row,
    set_focused_listing_option_index,
    sync_focused_listing_option,
)

_ROW_A = {
    "ID": "10",
    "Titulo": "Departamento en alquiler centro",
    "Tipo": "Departamento",
    "Barrio": "Centro",
    "Precio": "700000",
    "Caracteristicas": "Balcón",
}
_ROW_B = {
    "ID": "20",
    "Titulo": "Casa con patio en Campus",
    "Tipo": "Casa",
    "Barrio": "Campus",
    "Precio": "500000",
    "Caracteristicas": "Sin patio | Balcón interno",
}
_ROWS = [_ROW_A, _ROW_B]


def test_focused_option_resolves_ambiguous_price_question() -> None:
    capture = set_focused_listing_option_index({}, 2)
    row = resolve_listing_choice_row(
        "cual es el precio de alquiler?",
        _ROWS,
        capture_data=capture,
    )
    assert row is not None
    assert row["ID"] == "20"


def test_focused_option_cleared_on_new_listing() -> None:
    capture = set_focused_listing_option_index({}, 2)
    capture = merge_last_listing_into_capture(
        capture,
        property_ids=["10", "20"],
        branch="alquiler",
        catalog_path="data/rent.csv",
    )
    assert get_focused_listing_option_index(capture) is None


def test_sync_from_bot_cites_option() -> None:
    capture = sync_focused_listing_option(
        {},
        user_text="tiene patio?",
        bot_text="La Opción 2 no tiene patio. Incluye balcón interno.",
        listing_rows=_ROWS,
    )
    assert get_focused_listing_option_index(capture) == 2


def test_property_ref_uses_focused_option() -> None:
    capture = set_focused_listing_option_index({}, 2)
    ref = property_ref_from_listing_choice(
        "cuanto sale?",
        _ROWS,
        capture_data=capture,
    )
    assert ref == "20"


def test_llm_user_message_includes_focused_option() -> None:
    body = build_user_message_for_llm(
        "cual es el precio?",
        listing_followup=True,
        focused_option_index=2,
    )
    assert "Opción en foco" in body
    assert "Opción 2" in body


def test_clear_focused_option() -> None:
    capture = clear_focused_listing_option(
        set_focused_listing_option_index({}, 1),
    )
    assert get_focused_listing_option_index(capture) is None
