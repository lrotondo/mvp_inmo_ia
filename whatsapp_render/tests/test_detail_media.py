from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.catalog import get_property_row_by_ref, load_properties_for_catalog_path
from app.capture_flow import append_user_flow_message
from app.detail_media import (
    bot_promises_visual_material,
    enrich_detail_media_from_catalog,
    property_ref_for_detail_enrich,
    should_enrich_property_detail,
    strip_property_media_from_message,
    user_requests_property_detail,
)
from app.property_matching import extract_property_ref
from app.property_ficha import (
    build_detail_delivery_caption,
    build_detail_media_links_block,
    collect_media_link_buttons,
)
from app.session_state import user_wants_fresh_start

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"

FAKE_ROW = {
    "ID": "5",
    "Direccion": "Arana 200",
    "Barrio": "Estacion",
    "Precio": "98000",
    "Ambientes": "2",
    "Caracteristicas": "Planta baja | Patio con parilla",
    "foto_principal": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800",
    "url_link_fotos": "https://example.com/galeria",
    "url_link_video": "https://example.com/video",
    "Link_Fotos": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800",
}


def test_tenant_catalog_loads_without_disponible_column() -> None:
    rows = load_properties_for_catalog_path(TENANT_RENT)
    assert len(rows) >= 3


def test_extract_property_ref_arana_from_user_text() -> None:
    ref = extract_property_ref(
        "",
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path=TENANT_RENT,
        current_user_text="dale quiero mas info del arana al 200",
    )
    assert ref
    row = get_property_row_by_ref(TENANT_RENT, ref)
    assert row is not None
    assert "Arana" in str(row.get("Direccion", ""))


def test_property_ref_from_capture_when_user_asked_arana() -> None:
    capture = append_user_flow_message({}, "alquiler", "mas info del arana 200")
    ref = property_ref_for_detail_enrich(
        current_user_text="fotos del arana 200",
        outbound_message="Te paso el material visual",
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path=TENANT_RENT,
        catalog_csv_path=TENANT_RENT,
        capture_data=capture,
    )
    assert ref
    assert get_property_row_by_ref(TENANT_RENT, ref) is not None


def test_enrich_injects_links_when_bot_promises_gallery() -> None:
    msg = (
        "Te cuento la propiedad.\n\n"
        "Acá te paso el material visual completo 👇\n\n"
        "¿Te gustaría visitarla?"
    )
    with patch(
        "app.detail_media.get_property_row_by_ref",
        return_value=FAKE_ROW,
    ):
        out = enrich_detail_media_from_catalog(
            msg,
            catalog_csv_path=TENANT_RENT,
            property_ref="5",
            current_user_text="fotos o videos?",
            flow_path="alquiler",
            capture_data=append_user_flow_message(
                {}, "alquiler", "info del arana 200"
            ),
        )
    assert "http" not in out
    assert "[📸" not in out


def test_user_requests_fotos_detected() -> None:
    assert user_requests_property_detail("fotos o videos?")


def test_bot_promises_galeria_comparto() -> None:
    assert bot_promises_visual_material(
        "Ahora te comparto la galería completa de la propiedad de Arana 200 👇"
    )


def test_build_detail_delivery_caption_avoids_duplicate_header() -> None:
    intro = (
        "¡Buenísima elección! Es un piso amplio en *Sarmiento y Alem*.\n"
        "El precio es de *$850.000 mensuales* con expensas de *$150.000*."
    )
    row = {
        **FAKE_ROW,
        "Direccion": "Sarmiento y Alem",
        "Barrio": "Centro",
        "Precio": "850000",
        "Ambientes": "3 ambientes",
        "Caracteristicas": "Living comedor | Dos cocheras",
        "url_link_fotos": "https://example.com/galeria",
    }
    caption = build_detail_delivery_caption(row, intro=intro)
    assert "Excelente" in caption or "Sarmiento" in caption
    assert "Características" in caption
    buttons = collect_media_link_buttons(row)
    assert buttons
    assert any(
        "foto" in b.label.lower() or "instagram" in b.label.lower() for b in buttons
    )
    assert "Sarmiento y Alem" in caption
    assert "850000" in caption or "850" in caption


def test_try_deliver_sends_text_with_links_when_enriched() -> None:
    from app.detail_media import try_deliver_single_property_visual

    enriched = (
        "Disculpá.\n\n"
        "*Características:*\n• Patio\n"
        "¡Genial! Te dejo la galería completa 👇\n\n"
        "¿Qué te parece?"
    )

    async def _run() -> None:
        with (
            patch(
                "app.detail_media.get_property_row_by_ref",
                return_value=FAKE_ROW,
            ),
            patch(
                "app.detail_media.send_whatsapp_image_message",
                new_callable=AsyncMock,
            ) as mock_img,
            patch(
                "app.detail_media.send_whatsapp_cta_url_message",
                new_callable=AsyncMock,
            ) as mock_cta,
            patch(
                "app.detail_media.send_whatsapp_text_message",
                new_callable=AsyncMock,
            ) as mock_txt,
        ):
            result = await try_deliver_single_property_visual(
                access_token="tok",
                phone_number_id="pnid",
                to_wa_id="54911",
                message=enriched,
                catalog_csv_path=TENANT_RENT,
                current_user_text="no me mostraste fotos",
                flow_path="alquiler",
                capture_data=append_user_flow_message(
                    {}, "alquiler", "arana 200"
                ),
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                property_ref="5",
            )
            assert result is not None
            assert "Arana" in result
            assert "Material visual" in result or "álbum" in result.lower() or "Ver" in result
            assert mock_img.await_count == 1
            assert mock_cta.await_count >= 1
            assert mock_txt.await_count == 0
            assert "https://" not in mock_img.await_args.kwargs.get("caption", "")

    asyncio.run(_run())


def test_collect_media_link_buttons_album_and_video() -> None:
    row = {
        **FAKE_ROW,
        "foto_principal": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800",
        "url_link_fotos": "https://www.instagram.com/p/ABC123/",
        "url_link_video": "https://example.com/v",
    }
    buttons = collect_media_link_buttons(row)
    labels = [b.label for b in buttons]
    urls = [b.url for b in buttons]
    assert "📱 Instagram" in labels
    assert any("instagram.com" in u for u in urls)
    assert any("video" in label.lower() for label in labels)
    assert not any(u.endswith("?w=800") for u in urls)

    preview_cta = collect_media_link_buttons(row, include_preview_cta=True)
    assert any("foto" in b.label.lower() for b in preview_cta)


def test_try_deliver_single_image_with_cta_buttons() -> None:
    from app.detail_media import try_deliver_single_property_visual

    async def _run() -> None:
        with (
            patch(
                "app.detail_media.get_property_row_by_ref",
                return_value=FAKE_ROW,
            ),
            patch(
                "app.detail_media.send_whatsapp_image_message",
                new_callable=AsyncMock,
            ) as mock_img,
            patch(
                "app.detail_media.send_whatsapp_cta_url_message",
                new_callable=AsyncMock,
            ) as mock_cta,
            patch(
                "app.detail_media.send_whatsapp_text_message",
                new_callable=AsyncMock,
            ) as mock_txt,
        ):
            result = await try_deliver_single_property_visual(
                access_token="tok",
                phone_number_id="pnid",
                to_wa_id="54911",
                message=(
                    "¡Genial! Te cuento más sobre la de Arana 200.\n\n"
                    "¿Te gustaría visitarla?"
                ),
                catalog_csv_path=TENANT_RENT,
                current_user_text="mas detalles de arana 200",
                flow_path="alquiler",
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                property_ref="5",
            )
            assert result is not None
            assert mock_img.await_count == 1
            assert mock_cta.await_count >= 1
            assert mock_txt.await_count == 0
            caption = mock_img.await_args.kwargs.get("caption", "")
            assert "Arana" in caption or "arana" in caption.lower()
            assert "¿Te gustaría visitarla?" in caption
            assert "https://" not in caption

    asyncio.run(_run())
