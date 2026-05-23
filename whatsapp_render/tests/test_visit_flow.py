from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.conversation_flow import _resolve_visit_property_ref
from app.detail_media import should_deliver_property_detail_ficha
from app.listing_delivery import deliver_bot_response
from app.prompts.templates import format_visit_confirmation, is_visit_confirmation_message

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"

FAKE_ROW = {
    "ID": "8",
    "Titulo": "Departamento en primer piso ubicado al frente",
    "Direccion": "Saavedra al 700",
    "Barrio": "Centro",
    "Caracteristicas": "Living comedor, cocina separada",
}


def test_is_visit_confirmation_message() -> None:
    text = format_visit_confirmation("Saavedra al 700")
    assert is_visit_confirmation_message(text)
    assert not is_visit_confirmation_message("¿Te gustaría coordinar una visita?")


def test_resolve_visit_property_ref_prefers_title_over_numeric_id() -> None:
    capture = {
        "visit_property_ref": "8",
        "last_viewed_property": {
            "id": "8",
            "catalog_path": TENANT_RENT,
            "branch": "alquiler",
        },
    }
    with patch(
        "app.conversation_flow.load_last_viewed_property_row",
        return_value=FAKE_ROW,
    ):
        ref = _resolve_visit_property_ref(
            capture,
            catalog_path=TENANT_RENT,
        )
    assert ref == "Departamento en primer piso ubicado al frente"
    assert ref != "8"


def test_should_deliver_property_detail_ficha_false_on_visit_confirmation() -> None:
    message = format_visit_confirmation("Saavedra al 700")
    assert not should_deliver_property_detail_ficha(
        flow_path="alquiler",
        property_ref="8",
        row=FAKE_ROW,
        outbound_message=message,
        current_user_text="lunes a viernes por la tarde",
        capture_data={"intake_answered": True},
    )


def test_deliver_bot_response_skips_ficha_on_visit_confirmation() -> None:
    message = format_visit_confirmation("Saavedra al 700")

    async def _run() -> None:
        with (
            patch(
                "app.listing_delivery.try_deliver_single_property_visual",
                new_callable=AsyncMock,
            ) as mock_visual,
            patch(
                "app.listing_delivery.send_whatsapp_text_message",
                new_callable=AsyncMock,
            ) as mock_text,
            patch(
                "app.listing_delivery.send_whatsapp_image_message",
                new_callable=AsyncMock,
            ) as mock_image,
        ):
            result = await deliver_bot_response(
                access_token="tok",
                phone_number_id="pnid",
                to_wa_id="54911",
                message=message,
                catalog_csv_path=TENANT_RENT,
                current_user_text="lunes a viernes por la tarde",
                flow_path="alquiler",
                property_ref="8",
                capture_data={
                    "intake_answered": True,
                    "last_viewed_property": {
                        "id": "8",
                        "catalog_path": TENANT_RENT,
                        "branch": "alquiler",
                    },
                },
                skip_property_delivery=True,
            )
            assert "Registré tu interés" in result.text
            assert result.delivered_property_id == ""
            mock_visual.assert_not_called()
            mock_image.assert_not_called()
            mock_text.assert_awaited_once()
            assert mock_text.await_args.kwargs["message"] == message

    asyncio.run(_run())
