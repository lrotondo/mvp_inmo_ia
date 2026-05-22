from __future__ import annotations

from app.listing_context import (
    merge_last_listing_into_capture,
    property_ref_from_listing_choice,
    resolve_listing_choice_row,
)

MOCK_ROWS = [
    {
        "ID": "10",
        "Titulo": "Depto Saavedra",
        "Tipo": "Departamento",
        "Direccion": "Saavedra 100",
        "Barrio": "Centro",
    },
    {
        "ID": "11",
        "Titulo": "Depto Sarmiento",
        "Tipo": "Departamento",
        "Direccion": "Sarmiento 200",
        "Barrio": "Centro",
    },
    {
        "ID": "12",
        "Titulo": "Duplex Chacabuco",
        "Tipo": "Duplex",
        "Direccion": "Chacabuco 300",
        "Barrio": "Norte",
    },
]


def test_resolve_duplex_from_listing_scope() -> None:
    row = resolve_listing_choice_row("el duplex me interesa", MOCK_ROWS)
    assert row is not None
    assert row["ID"] == "12"


def test_resolve_la_segunda_from_listing_scope() -> None:
    row = resolve_listing_choice_row("tenes mas fotos de la segunda?", MOCK_ROWS)
    assert row is not None
    assert row["ID"] == "11"


def test_resolve_opcion_2_phrase() -> None:
    row = resolve_listing_choice_row("mas fotos de la opcion 2?", MOCK_ROWS)
    assert row is not None
    assert row["ID"] == "11"


def test_property_ref_from_listing_choice() -> None:
    ref = property_ref_from_listing_choice("me interesa la opción 2", MOCK_ROWS)
    assert ref == "11"


def test_merge_last_listing_into_capture() -> None:
    merged = merge_last_listing_into_capture(
        {},
        property_ids=["10", "11", "12"],
        branch="alquiler",
        catalog_path="data/tenants/x.csv",
    )
    assert merged["last_listing"]["ids"] == ["10", "11", "12"]
