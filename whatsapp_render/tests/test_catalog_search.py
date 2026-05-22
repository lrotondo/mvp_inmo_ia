from __future__ import annotations

from app.catalog import load_properties_for_catalog_path
from app.catalog_search import (
    filter_catalog_rows,
    parse_search_criteria,
    pick_listing_ids,
    select_listing_candidates,
)
from app.listing_delivery import ensure_listado_from_candidates, strip_invented_listings

SALE_CSV = "data/tenants/inmobiliaria_cowork.csv"


def test_parse_criteria_leo_scenario() -> None:
    blob = (
        "no tengo preferencia de zona, preferiria una casa, de 2 o mas dormitorios\n"
        "tengo 200000"
    )
    criteria = parse_search_criteria(blob, branch="compra")
    assert criteria.any_zone is True
    assert criteria.property_type == "casa"
    assert criteria.min_bedrooms == 2
    assert criteria.max_price_usd == 200_000


def test_filter_casa_under_200k_returns_real_ids() -> None:
    rows = load_properties_for_catalog_path(SALE_CSV)
    blob = (
        "no tengo preferencia de zona, casa, 2 o mas dormitorios, tengo 200000"
    )
    criteria = parse_search_criteria(blob, branch="compra")
    filtered = filter_catalog_rows(rows, criteria, "compra")
    ids = pick_listing_ids(filtered, max_items=5)
    assert ids
    assert all(pid.isdigit() for pid in ids)
    assert "9778241" in ids or "9764933" in ids or "9893593" in ids
    for row in filtered[:5]:
        assert "casa" in str(row.get("Tipo", "")).lower() or "casa" in str(
            row.get("Titulo", "")
        ).lower()


def test_select_listing_candidates_integration() -> None:
    rows = load_properties_for_catalog_path(SALE_CSV)
    blob = "cualquier zona, casa, 2 dormitorios, usd 200000"
    ids, picked = select_listing_candidates(rows, blob, branch="compra")
    assert len(ids) <= 3
    assert len(picked) == len(ids)


def test_strip_invented_listings_removes_fake_zones() -> None:
    msg = (
        "¡Perfecto!\n\n"
        "- Casa en *Zona Norte*, 2 dormitorios, USD 185.000.\n"
        "- Casa en *Zona Oeste*, 3 dormitorios, USD 195.000.\n\n"
        "¿Te interesa alguna?"
    )
    out = strip_invented_listings(msg)
    assert "Zona Norte" not in out
    assert "USD 185" not in out
    assert "¿Te interesa" in out


def test_ensure_listado_injects_backend_ids() -> None:
    msg = (
        "¡Perfecto, vamos encaminados!\n\n"
        "- Casa en *Zona Norte*, 2 dormitorios, USD 185.000.\n\n"
        "¿Alguna te llama la atención?"
    )
    out = ensure_listado_from_candidates(
        msg,
        ["9778241", "9764933", "9893593"],
        SALE_CSV,
    )
    assert "[LISTADO:9778241,9764933,9893593]" in out
    assert "Zona Norte" not in out
