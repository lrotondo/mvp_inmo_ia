from __future__ import annotations

from unittest.mock import patch

from app.catalog import field_matches_reference, find_property_row_for_user_text
from app.capture_flow import append_user_flow_message
from app.detail_media import (
    resolve_detail_property_row,
    user_reports_missing_media,
    user_requests_property_detail,
)
from app.listing_context import merge_last_listing_into_capture

NOGALES_ROW = {
    "ID": "42",
    "Titulo": "Casa en country",
    "Direccion": "Los Nogales y Los Tilos",
    "Barrio": "Country",
    "Precio": "300000",
    "Ambientes": "4",
    "Caracteristicas": "Pileta | Parrilla",
    "foto_principal": "https://images.wasi.co/photo.jpg",
    "url_link_fotos": "https://www.instagram.com/p/abc/",
    "url_link_video": "https://example.com/v.mp4",
}


def test_field_matches_partial_address() -> None:
    assert field_matches_reference("los nogales", "Los Nogales y Los Tilos")
    assert field_matches_reference(
        "me interesa la que está ubicada en los nogales",
        "Los Nogales y Los Tilos",
    )


def test_find_row_for_user_text_nogales() -> None:
    row = find_property_row_for_user_text(
        None,
        "Me interesa la que está ubicada en los nogales",
        rows_scope=[NOGALES_ROW],
    )
    assert row is not None
    assert row["ID"] == "42"


def test_missing_media_triggers_detail() -> None:
    assert user_reports_missing_media("No veo las fotos")
    assert user_requests_property_detail("No veo las fotos")


def test_resolve_from_last_listing_in_capture() -> None:
    capture = merge_last_listing_into_capture(
        {},
        property_ids=["99", "42"],
        branch="alquiler",
        catalog_path="data/catalog.csv",
    )

    with patch(
        "app.listing_context.load_last_listing_rows",
        return_value=[{"ID": "99"}, NOGALES_ROW],
    ):
        row = resolve_detail_property_row(
            catalog_csv_path="data/catalog.csv",
            current_user_text="me interesa la opción 2",
            outbound_message="Te paso el material visual 👇",
            property_ref="",
            flow_path="alquiler",
            catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
            catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
            capture_data=capture,
        )
    assert row is not None
    assert row["ID"] == "42"
