from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.catalog import get_property_row_by_ref
from app.conversation import HistoryTurn
from app.detail_media import (
    bot_promises_visual_material,
    enrich_detail_media_from_catalog,
    should_enrich_property_detail,
    strip_property_media_from_message,
    user_showed_property_interest,
)
from app.property_ficha import build_detail_media_links_block
from app.session_state import user_wants_fresh_start

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"

FAKE_ROW = {
    "ID": "2",
    "Direccion": "Chacabuco 800",
    "Barrio": "Centro",
    "Precio": "240000",
    "Ambientes": "4",
    "Caracteristicas": "Balcón | Ascensor | Luminoso",
    "foto_principal": "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800",
    "url_link_fotos": "https://example.com/galeria",
    "url_link_video": "https://example.com/video",
}


def test_fresh_start_detected() -> None:
    assert user_wants_fresh_start("Empecemos de nuevo")


def test_bot_promises_visual_material_detected() -> None:
    msg = "Te paso el material visual para que la conozcas mejor:"
    assert bot_promises_visual_material(msg)


def test_should_enrich_on_property_interest_and_visual_promise() -> None:
    outbound = (
        "¡Excelente elección! La de Chacabuco 800.\n\n"
        "Te paso el material visual para que la conozcas mejor:\n\n"
        "¿Coordinamos visita?"
    )
    assert should_enrich_property_detail(
        outbound_message=outbound,
        current_user_text="me gusta la de Chacabuco",
        flow_path="alquiler",
    )


def test_should_not_enrich_on_fresh_start() -> None:
    assert not should_enrich_property_detail(
        outbound_message="Te paso el material visual",
        current_user_text="Empecemos de nuevo",
        flow_path="compra",
    )


def test_strip_removes_orphan_media_on_triage() -> None:
    triage = (
        "¿Comprar o alquilar?\n"
        "[📸 Ver galería de fotos](https://example.com/g)\n"
    )
    out = strip_property_media_from_message(triage)
    assert "example.com" not in out


def test_enrich_adds_ficha_when_visual_promised() -> None:
    msg = (
        "¡Excelente elección! La de Chacabuco 800.\n\n"
        "Te paso el material visual para que la conozcas mejor:\n\n"
        "¿Te gustaría coordinar una visita?"
    )
    with patch(
        "app.detail_media.get_property_row_by_ref",
        return_value=FAKE_ROW,
    ):
        out = enrich_detail_media_from_catalog(
            msg,
            catalog_csv_path=TENANT_RENT,
            property_ref="2",
            current_user_text="me interesa la de Chacabuco",
            flow_path="alquiler",
            history=[],
        )
    assert "Características" in out
    assert "Ver galería" in out
    assert user_showed_property_interest("me interesa la de Chacabuco")


def test_try_deliver_sends_image_and_text() -> None:
    from app.detail_media import try_deliver_single_property_visual

    msg = (
        "¡Excelente elección!\n\n"
        "Te paso el material visual:\n\n"
        "¿Preferís mañana o tarde?"
    )
    enriched = (
        "¡Excelente elección!\n\n"
        "Te paso el material visual:\n\n"
        "*Características:*\n• Balcón\n"
        "Acá tenés todo el material visual 👇\n"
        "[📸 Ver galería de fotos](https://example.com/galeria)\n"
        "[🎥 Ver video](https://example.com/video)\n\n"
        "¿Preferís mañana o tarde?"
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
                current_user_text="me gusta Chacabuco 800",
                flow_path="alquiler",
                history=[],
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                property_ref="2",
            )
            assert result is not None
            mock_img.assert_awaited_once()
            mock_txt.assert_awaited_once()

    asyncio.run(_run())


def test_build_detail_media_links_block() -> None:
    block = build_detail_media_links_block(FAKE_ROW)
    assert "galería" in block
    assert "video" in block


def test_get_property_row_by_ref_finds_id() -> None:
    row = get_property_row_by_ref(TENANT_RENT, "4")
    assert row is not None
    assert str(row.get("ID")) == "4"
