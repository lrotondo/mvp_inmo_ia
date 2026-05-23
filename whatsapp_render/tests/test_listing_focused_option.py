from __future__ import annotations

from app.conversation import build_user_message_for_llm
from app.listing_context import (
    clear_focused_listing_option,
    get_focused_listing_option_index,
    get_last_viewed_property_id,
    merge_last_listing_into_capture,
    property_ref_from_listing_choice,
    resolve_listing_choice_row,
    set_focused_listing_option_index,
    set_last_viewed_property,
    sync_focused_listing_option,
    user_asks_listing_attribute_followup,
)
from app.detail_media import should_enrich_property_detail

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


def test_last_viewed_resolves_post_detail_followup() -> None:
    from unittest.mock import patch

    capture = {
        "last_listing": {
            "ids": ["10", "20"],
            "branch": "alquiler",
            "catalog_path": "data/rent.csv",
        },
        "last_viewed_property": {
            "id": "20",
            "catalog_path": "data/rent.csv",
            "branch": "alquiler",
        },
    }

    def _fake_get_properties(
        _path: str | None,
        property_ids: list[str],
        *,
        max_items: int = 3,
    ) -> list[dict]:
        by_id = {str(r["ID"]): r for r in _ROWS}
        return [by_id[pid] for pid in property_ids if pid in by_id][:max_items]

    with patch(
        "app.listing_context.get_properties_by_ids",
        side_effect=_fake_get_properties,
    ):
        row = resolve_listing_choice_row(
            "cual es el precio de alquiler? aceptan mascotas?",
            _ROWS,
            capture_data=capture,
        )
    assert row is not None
    assert row["ID"] == "20"


def test_attribute_followup_skips_detail_enrich() -> None:
    capture = set_last_viewed_property(
        {},
        property_id="20",
        catalog_path="data/rent.csv",
        branch="alquiler",
    )
    assert user_asks_listing_attribute_followup(
        "cual es el precio de alquiler? aceptan mascotas?"
    )
    assert not should_enrich_property_detail(
        outbound_message="Te dejo la galería completa 👇",
        current_user_text="cual es el precio de alquiler? aceptan mascotas?",
        flow_path="alquiler",
        capture_data=capture,
    )
    assert get_last_viewed_property_id(capture) == "20"
