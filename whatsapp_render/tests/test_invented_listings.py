from __future__ import annotations

from app.capture_flow import append_user_flow_message
from app.catalog import load_properties_for_catalog_path
from app.catalog_search import select_listing_candidates
from app.catalog_search import user_declined_zone_preference
from app.search_profile import user_search_profile_ready
from app.listing_delivery import strip_invented_listings, ensure_listado_from_candidates

SALE_CSV = "data/tenants/inmobiliaria_cowork.csv"
RENT_CSV = "data/tenants/inmobiliaria_cowork_alquiler.csv"


def test_zonas_preferidas_counts_as_any_zone() -> None:
    assert user_declined_zone_preference("no tengo zonas preferidas")


def test_profile_ready_casa_alquiler_sin_zona() -> None:
    capture = append_user_flow_message(
        {}, "alquiler", "busco casa 2 o 3 dormitorios en alquiler"
    )
    assert user_search_profile_ready(
        "quiero ver ideas, no tengo zonas preferidas",
        "alquiler",
        capture_data=capture,
    )


def test_select_casa_alquiler_two_or_three_beds() -> None:
    rows = load_properties_for_catalog_path(RENT_CSV)
    blob = (
        "busco casa 2 o 3 dormitorios en alquiler\n"
        "quiero ver ideas, no tengo zonas preferidas"
    )
    ids, _ = select_listing_candidates(rows, blob, branch="alquiler")
    assert "5" in ids or "8" in ids


def test_strip_villa_urquiza_style_list() -> None:
    msg = (
        "Te tiro las opciones:\n\n"
        "1. *Casa en Villa Urquiza* – 2 dormitorios, $350.000/mes\n"
        "2. *Casa en Caballito* – 3 dormitorios, $420.000/mes\n\n"
        "¿Cuál te llama más la atención?"
    )
    out = strip_invented_listings(msg)
    assert "Villa Urquiza" not in out
    assert "350.000" not in out
    assert "llama más la atención" in out


def test_ensure_listado_injects_real_rent_ids() -> None:
    rows = load_properties_for_catalog_path(RENT_CSV)
    blob = "casa 2 o 3 dormitorios, no tengo zonas preferidas"
    ids, _ = select_listing_candidates(rows, blob, branch="alquiler")
    assert ids
    msg = (
        "1. *Casa en Villa Urquiza* – 2 dormitorios, $350.000/mes\n"
        "¿Cuál te interesa?"
    )
    out = ensure_listado_from_candidates(msg, ids, RENT_CSV)
    assert "[LISTADO:" in out
    assert "Villa Urquiza" not in out
    for pid in ids:
        assert pid in out
