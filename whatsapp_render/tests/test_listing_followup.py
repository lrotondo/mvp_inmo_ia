from __future__ import annotations

from app.conversation import HistoryTurn
from app.listing_context import (
    listing_already_shown,
    user_asks_about_shown_listing,
    user_requests_fresh_listing,
)
from app.turn_handler import TurnKind, resolve_turn_kind
from app.search_profile import SearchProfile


def _complete_profile() -> SearchProfile:
    return SearchProfile(
        branch="alquiler",
        property_type="departamento",
        min_bedrooms=2,
        any_zone=True,
        missing_fields=(),
    )


def test_followup_not_listing_after_listado_in_history() -> None:
    history = [
        HistoryTurn(
            role="assistant",
            content="Te paso opciones\n\n[LISTADO:1,2,3]\n\n¿Cuál te llama?",
        ),
    ]
    kind = resolve_turn_kind(
        "alquiler",
        profile=_complete_profile(),
        current_user_text="la opción 2 tiene pileta?",
        history=history,
        capture_data=None,
        catalog_path_used="data/x.csv",
    )
    assert kind == TurnKind.GENERAL


def test_fresh_listing_request_stays_listing() -> None:
    history = [
        HistoryTurn(role="assistant", content="[LISTADO:1,2,3]"),
    ]
    kind = resolve_turn_kind(
        "alquiler",
        profile=_complete_profile(),
        current_user_text="mostrame otras opciones",
        history=history,
        capture_data={"last_listing": {"ids": ["1", "2", "3"], "catalog_path": "x"}},
        catalog_path_used="x",
    )
    assert kind == TurnKind.LISTING


def test_listing_helpers() -> None:
    assert user_asks_about_shown_listing("cuántos metros tiene la segunda?")
    assert user_requests_fresh_listing("qué tenés disponible?")
    assert listing_already_shown(
        catalog_csv_path=None,
        capture_data={"last_listing": {"ids": ["1"], "catalog_path": "p"}},
        history=[],
    )
