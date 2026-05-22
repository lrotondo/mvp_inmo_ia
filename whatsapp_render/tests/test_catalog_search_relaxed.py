from __future__ import annotations

from app.catalog_search import (
    ListingFilterCriteria,
    filter_catalog_rows_relaxed,
    is_consultar_price,
    parse_property_types_from_blob,
    _classify_row_property_kind,
)


def test_is_consultar_price() -> None:
    assert is_consultar_price({"Precio": "Consultar"})
    assert not is_consultar_price({"Precio": "US$ 100.000"})


def test_parse_lote_type() -> None:
    assert "lote" in parse_property_types_from_blob("busco un lote en tandil")


def test_classify_lote_row() -> None:
    row = {"Tipo": "Lote", "Titulo": "Parcela 5 ha"}
    assert _classify_row_property_kind(row) == "lote"


def test_relaxed_filter_keeps_consultar_price_over_budget() -> None:
    rows = [
        {
            "ID": "1",
            "Tipo": "Casa",
            "Titulo": "Casa centro",
            "Precio": "Consultar",
            "Dormitorios": "3",
            "Zona": "Centro",
        },
        {
            "ID": "2",
            "Tipo": "Casa",
            "Titulo": "Casa cara",
            "Precio": "US$ 500.000",
            "Dormitorios": "3",
            "Zona": "Centro",
        },
    ]
    criteria = ListingFilterCriteria(
        property_types=("casa",),
        min_bedrooms=2,
        max_price_usd=100_000,
        zone_tokens=("centro",),
    )
    filtered = filter_catalog_rows_relaxed(rows, criteria, "compra")
    ids = [r["ID"] for r in filtered]
    assert "1" in ids
    assert "2" not in ids
