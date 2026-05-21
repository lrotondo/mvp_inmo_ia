from __future__ import annotations

from unittest.mock import patch

from app.catalog import field_matches_reference, find_property_row_for_user_text
from app.conversation import HistoryTurn
from app.detail_media import (
    _rows_from_recent_listado,
    resolve_detail_property_row,
    user_reports_missing_media,
    user_requests_property_detail,
)

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


def test_resolve_from_history_when_user_asked_nogales() -> None:
    history = [
        HistoryTurn(
            role="user",
            content="Me interesa la que está ubicada en los nogales",
        ),
    ]

    def fake_find(
        _path: str | None,
        text: str,
        *,
        rows_scope: list | None = None,
    ):
        if "nogales" in text.lower():
            return NOGALES_ROW
        return None

    with patch("app.detail_media.find_property_row_for_user_text", side_effect=fake_find):
        row = resolve_detail_property_row(
            catalog_csv_path="any.csv",
            current_user_text="No veo las fotos",
            outbound_message="Te paso el material visual 👇",
            history=history,
            property_ref="",
            flow_path="alquiler",
            catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
            catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
        )
    assert row is not None
    assert row["ID"] == "42"


def test_rows_from_recent_listado_parses_ids() -> None:
    history = [
        HistoryTurn(
            role="assistant",
            content="Opciones:\n\n[LISTADO:99,42]\n\n¿Cuál te interesa?",
        ),
    ]
    with patch(
        "app.detail_media.get_properties_by_ids",
        return_value=[NOGALES_ROW],
    ):
        rows = _rows_from_recent_listado(history, "data/catalog.csv")
    assert len(rows) == 1
    assert rows[0]["ID"] == "42"
