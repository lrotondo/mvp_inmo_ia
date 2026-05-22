from __future__ import annotations

from app.conversation import HistoryTurn
from app.lead_context import user_search_profile_ready
from app.listing_delivery import suppress_premature_catalog_outbound


def test_profile_not_ready_on_generic_rent_intent() -> None:
    history = [
        HistoryTurn(role="user", content="buen dia"),
        HistoryTurn(role="assistant", content="¿Comprar, alquilar o vender?"),
    ]
    assert not user_search_profile_ready(
        history,
        "estoy buscando departamento en alquiler",
        "alquiler",
    )


def test_profile_ready_with_zone_and_beds() -> None:
    history: list[HistoryTurn] = []
    assert user_search_profile_ready(
        history,
        "busco en el centro, 2 dormitorios",
        "alquiler",
    )


def test_profile_ready_any_zone_declared() -> None:
    assert user_search_profile_ready(
        [],
        "cualquier zona, monoambiente",
        "compra",
    )


def test_suppress_strips_listado_when_profile_incomplete() -> None:
    msg = (
        "¡Buen día! Te muestro una opción:\n\n"
        "[LISTADO:99]\n\n"
        "Garibaldi | Precio: $700000 | 1 dormitorios\n\n"
        "¿En qué zona te gustaría vivir?"
    )
    out = suppress_premature_catalog_outbound(
        msg,
        history=[],
        current_user_text="estoy buscando departamento en alquiler",
        flow_path="alquiler",
    )
    assert "[LISTADO:" not in out
    assert "Garibaldi" not in out
    assert "zona" in out.lower()
