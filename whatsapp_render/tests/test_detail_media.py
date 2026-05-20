from __future__ import annotations

from app.catalog import get_property_row_by_ref
from app.detail_media import (
    build_detail_media_block,
    enrich_detail_media_from_catalog,
    ensure_detail_includes_video,
    message_offers_property_gallery,
    message_offers_property_video,
)

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"


def test_build_detail_media_block_gallery_and_video() -> None:
    row = {
        "url_link_fotos": "https://example.com/galeria",
        "url_link_video": "https://example.com/video",
    }
    block = build_detail_media_block(row)
    assert "galería de fotos" in block
    assert "Ver video" in block
    assert "example.com/galeria" in block
    assert "example.com/video" in block


def test_get_property_row_by_ref_finds_id() -> None:
    row = get_property_row_by_ref(TENANT_RENT, "4")
    assert row is not None
    assert str(row.get("ID")) == "4"


def test_ensure_detail_appends_video_with_mock_row() -> None:
    msg = (
        "Detalle de la propiedad.\n\n"
        "[📸 Ver galería de fotos](https://example.com/fotos)"
    )

    class FakeCatalog:
        pass

    from unittest.mock import patch

    fake_row = {
        "ID": "99",
        "url_link_fotos": "https://example.com/fotos",
        "url_link_video": "https://example.com/video.mp4",
    }
    with patch(
        "app.detail_media.get_property_row_by_ref",
        return_value=fake_row,
    ):
        out = ensure_detail_includes_video(
            msg,
            catalog_csv_path=TENANT_RENT,
            property_ref="99",
        )
    assert message_offers_property_video(out)
    assert "example.com/video.mp4" in out


def test_enrich_inserts_full_block_when_no_links() -> None:
    msg = "Casa de 4 ambientes con pileta y jardín amplio."

    fake_row = {
        "ID": "4",
        "url_link_fotos": "https://example.com/g",
        "url_link_video": "https://example.com/v",
        "foto_principal": "https://example.com/p",
    }
    from unittest.mock import patch

    with patch(
        "app.detail_media.get_property_row_by_ref",
        return_value=fake_row,
    ):
        out = enrich_detail_media_from_catalog(
            msg,
            catalog_csv_path=TENANT_RENT,
            property_ref="4",
        )
    assert message_offers_property_gallery(out)
    assert message_offers_property_video(out)
