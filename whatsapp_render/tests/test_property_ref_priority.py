from __future__ import annotations

from unittest.mock import patch

from app.conversation import HistoryTurn
from app.lead_context import extract_property_ref
from app.property_ficha import (
    build_detail_delivery_caption,
    intro_conflicts_with_catalog_row,
    sanitize_detail_intro_for_row,
)

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"

GARIBALDI_ROW = {
    "ID": "99",
    "Titulo": "Departamento a estrenar en alquiler",
    "Direccion": "Garibaldi y 4 de Abril",
    "Barrio": "Centro",
    "Precio": "700000",
    "Dormitorios": "1",
    "Ambientes": "1 ambientes",
    "Caracteristicas": "Living comedor | Balcón | Cochera",
}

SANTA_MARIA_ROW = {
    "ID": "88",
    "Titulo": "Casa de 1 habitación con cochera",
    "Direccion": "Santa María de Oro al 100",
    "Barrio": "Calvario",
    "Precio": "500000",
    "Dormitorios": "1",
    "Ambientes": "2 ambientes",
    "Caracteristicas": "Patio | Cochera",
}

_CATALOG_ROWS = [GARIBALDI_ROW, SANTA_MARIA_ROW]


def test_extract_property_ref_prioritizes_current_message() -> None:
    history = [
        HistoryTurn(
            role="user",
            content="me interesa la de Santa María de Oro al 100",
        ),
    ]
    with (
        patch(
            "app.lead_context.catalog_paths_for_flow",
            return_value=[TENANT_RENT],
        ),
        patch(
            "app.catalog.iter_rows_for_property_matching",
            return_value=_CATALOG_ROWS,
        ),
    ):
        ref = extract_property_ref(
            "",
            flow_path="alquiler",
            catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
            catalog_rent_path=TENANT_RENT,
            history=history,
            current_user_text="te pedi info de la de garibaldi y 4 de abril",
            user_only=True,
        )
    assert "Garibaldi" in ref
    assert "Santa" not in ref


def test_intro_conflicts_detects_wrong_property_description() -> None:
    intro = (
        "Te cuento sobre la Casa de 1 habitación con cochera en "
        "Santa María de Oro al 100, barrio Calvario."
    )
    with patch(
        "app.catalog.iter_rows_for_property_matching",
        return_value=_CATALOG_ROWS,
    ):
        assert intro_conflicts_with_catalog_row(intro, GARIBALDI_ROW, "any.csv")


def test_sanitize_detail_intro_drops_wrong_property_text() -> None:
    intro = (
        "¡Uy, disculpame! Me confundí al responder.\n\n"
        "Te cuento sobre la *Casa de 1 habitación con cochera* en "
        "*Santa María de Oro al 100*, barrio Calvario.\n\n"
        "Es una casa súper práctica con patio y cochera."
    )
    with patch(
        "app.catalog.iter_rows_for_property_matching",
        return_value=_CATALOG_ROWS,
    ):
        cleaned = sanitize_detail_intro_for_row(intro, GARIBALDI_ROW, "any.csv")
        assert "disculp" in cleaned.lower()
        assert "santa maría" not in cleaned.lower()

        caption = build_detail_delivery_caption(
            GARIBALDI_ROW,
            intro=intro,
            catalog_csv_path="any.csv",
            include_media_links=False,
        )
        assert "Garibaldi" in caption
        assert "santa maría de oro" not in caption.lower()
