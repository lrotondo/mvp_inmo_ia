from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.listing_delivery import BotDeliveryResult, deliver_bot_response
from app.property_ficha import collect_media_link_buttons

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"


def test_collect_buttons_includes_instagram_when_primary_is_direct_image() -> None:
    row = {
        "ID": "5",
        "Direccion": "Chacabuco 1000",
        "foto_principal": "https://cdn.example.com/preview.jpg",
        "url_link_fotos": "https://www.instagram.com/p/ABC123/",
        "url_link_video": "https://example.com/video.mp4",
    }
    buttons = collect_media_link_buttons(row)
    labels = [b.label for b in buttons]
    urls = [b.url for b in buttons]
    assert "📱 Instagram" in labels
    assert any("instagram.com" in u for u in urls)
    assert any("video" in lbl.lower() for lbl in labels)


def test_detail_intent_before_listado_delivery() -> None:
    msg = (
        "¡Excelente elección!\n\n"
        "[LISTADO:9]\n\n"
        "Acá te paso la ficha y material visual 👇"
    )

    async def _run() -> None:
        with (
            patch(
                "app.listing_delivery.try_deliver_single_property_visual",
                new_callable=AsyncMock,
                return_value="Ficha detalle enviada",
            ) as mock_detail,
            patch(
                "app.listing_delivery.send_whatsapp_image_message",
                new_callable=AsyncMock,
            ) as mock_list_img,
        ):
            result = await deliver_bot_response(
                access_token="tok",
                phone_number_id="pnid",
                to_wa_id="54911",
                message=msg,
                catalog_csv_path=TENANT_RENT,
                current_user_text="me gusta la de chacabuco al 1000, tenes mas info?",
                flow_path="alquiler",
            )
            assert mock_detail.await_count == 1
            mock_list_img.assert_not_awaited()
            assert isinstance(result, BotDeliveryResult)
            assert "[LISTADO:" not in result.text
            assert "Ficha detalle" in result.text
            assert result.delivered_property_id in ("", "9")

    asyncio.run(_run())
