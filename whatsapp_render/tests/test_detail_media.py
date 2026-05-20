from __future__ import annotations

from unittest.mock import patch

from app.catalog import get_property_row_by_ref
from app.conversation import HistoryTurn
from app.detail_media import (
    enrich_detail_media_from_catalog,
    should_enrich_property_detail,
    strip_property_media_from_message,
    user_requests_property_detail,
)
from app.property_ficha import build_detail_media_links_block
from app.session_state import user_wants_fresh_start

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"


def test_fresh_start_detected() -> None:
    assert user_wants_fresh_start("Empecemos de nuevo")
    assert user_wants_fresh_start("quiero empezar de nuevo")


def test_should_not_enrich_on_fresh_start_triage() -> None:
    triage = (
        "¿En qué te puedo ayudar? ¿Comprar, alquilar o vender?\n\n"
        "Acá tenés todo el material visual 👇\n"
        "[📸 Ver galería de fotos](https://example.com/g)\n"
        "[🎥 Ver video](https://example.com/v)"
    )
    assert not should_enrich_property_detail(
        outbound_message=triage,
        current_user_text="Empecemos de nuevo",
        flow_path="compra",
    )


def test_strip_removes_media_from_triage_reply() -> None:
    triage = (
        "¡Hola! ¿Comprar, alquilar o vender?\n\n"
        "Acá tenés todo el material visual 👇\n"
        "[📸 Ver galería de fotos](https://example.com/g)\n"
        "[🎥 Ver video](https://example.com/v)"
    )
    out = strip_property_media_from_message(triage)
    assert "example.com" not in out
    assert "material visual" not in out
    assert "Comprar" in out


def test_enrich_skips_fresh_start_even_with_history_property() -> None:
    msg = (
        "¿En qué te puedo ayudar?\n"
        "[📸 Ver galería de fotos](https://example.com/g)"
    )
    history = [
        HistoryTurn(role="user", content="me interesa la de Don Bosco 1800"),
    ]
    fake_row = {
        "ID": "4",
        "Direccion": "Av. Don Bosco 1800",
        "Caracteristicas": "Pileta",
        "url_link_fotos": "https://example.com/g",
    }
    with patch(
        "app.detail_media.get_property_row_by_ref",
        return_value=fake_row,
    ):
        out = enrich_detail_media_from_catalog(
            msg,
            catalog_csv_path=TENANT_RENT,
            property_ref="4",
            current_user_text="Empecemos de nuevo",
            flow_path="compra",
            history=history,
        )
    assert "example.com" not in out


def test_enrich_detail_on_explicit_detail_request() -> None:
    msg = "Te cuento más de esa propiedad."
    fake_row = {
        "ID": "4",
        "Direccion": "Av. Don Bosco 1800",
        "Barrio": "Don Bosco",
        "Precio": "380000",
        "Ambientes": "4",
        "Caracteristicas": "Pileta | Jardin",
        "url_link_fotos": "https://example.com/g",
        "url_link_video": "https://example.com/v",
    }
    with patch(
        "app.detail_media.get_property_row_by_ref",
        return_value=fake_row,
    ):
        out = enrich_detail_media_from_catalog(
            msg,
            catalog_csv_path=TENANT_RENT,
            property_ref="4",
            current_user_text="contame más de la opción 4",
            flow_path="alquiler",
            history=[
                HistoryTurn(role="user", content="me gusta la opción 4"),
            ],
        )
    assert "Características" in out
    assert "Ver galería" in out
    assert user_requests_property_detail("contame más de la opción 4")


def test_build_detail_media_links_block_gallery_and_video() -> None:
    row = {
        "url_link_fotos": "https://example.com/galeria",
        "url_link_video": "https://example.com/video",
    }
    block = build_detail_media_links_block(row)
    assert "galería de fotos" in block
    assert "Ver video" in block


def test_get_property_row_by_ref_finds_id() -> None:
    row = get_property_row_by_ref(TENANT_RENT, "4")
    assert row is not None
    assert str(row.get("ID")) == "4"
