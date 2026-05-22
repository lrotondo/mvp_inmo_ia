from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.catalog import get_properties_by_ids
from app.listing_delivery import (
    build_listing_caption,
    consolidate_history_text,
    deliver_bot_response,
    ensure_listado_from_candidates,
    parse_listado_tag,
    strip_listado_tags,
)
from app.meta_client import is_public_https_image_url

TENANT_RENT = "data/tenants/inmobiliaria_cowork_alquiler.csv"


def test_parse_listado_tag_splits_intro_ids_closing() -> None:
    text = (
        "¡Perfecto! Opciones en alquiler:\n\n"
        "[LISTADO:4, 2, 3]\n\n"
        "¿Cuál te interesa?"
    )
    parsed = parse_listado_tag(text)
    assert parsed is not None
    assert parsed.intro.startswith("¡Perfecto!")
    assert parsed.property_ids == ["4", "2", "3"]
    assert "¿Cuál te interesa?" in parsed.closing
    assert "[LISTADO:" not in parsed.text_without_tag


def test_parse_listado_tag_none_without_tag() -> None:
    assert parse_listado_tag("Solo texto sin tag") is None


def test_strip_listado_tags() -> None:
    text = "Intro\n\n[LISTADO:1,8,9]\n\n¿Cuál te interesa?"
    assert "[LISTADO:" not in strip_listado_tags(text)
    assert "Intro" in strip_listado_tags(text)


def test_listado_skips_detail_delivery() -> None:
    msg = "[LISTADO:1,8]\n\n¿Cuál te llama más la atención?"

    async def _run() -> None:
        with (
            patch(
                "app.listing_delivery.try_deliver_single_property_visual",
                new_callable=AsyncMock,
            ) as mock_detail,
            patch(
                "app.listing_delivery.send_whatsapp_text_message",
                new_callable=AsyncMock,
            ),
            patch(
                "app.listing_delivery.send_whatsapp_image_message",
                new_callable=AsyncMock,
            ) as mock_image,
        ):
            await deliver_bot_response(
                access_token="tok",
                phone_number_id="pnid",
                to_wa_id="54911",
                message=msg,
                catalog_csv_path=TENANT_RENT,
                current_user_text="cualquier zona, departamento, 2 dormitorios",
                flow_path="alquiler",
            )
            mock_detail.assert_not_awaited()
            assert mock_image.await_count >= 1

    asyncio.run(_run())


def test_get_properties_by_ids_preserves_order() -> None:
    rows = get_properties_by_ids(TENANT_RENT, ["8", "4", "99"])
    ids = [str(r.get("ID")) for r in rows]
    assert ids == ["8", "4"]


def test_build_listing_caption_includes_location_and_tour() -> None:
    row = {
        "Direccion": "Av. Don Bosco 1800",
        "Barrio": "Don Bosco",
        "Precio": "380000",
        "Ambientes": "4",
        "Caracteristicas": "Casa - Jardin",
        "Tour_360": "https://example.com/tour",
    }
    cap = build_listing_caption(row, 1)
    assert "Opción 1" in cap
    assert "Don Bosco" in cap
    assert "380000" in cap or "380.000" in cap
    assert "Tour 360" in cap


def test_is_public_https_image_url() -> None:
    assert is_public_https_image_url("https://images.unsplash.com/photo.jpg")
    assert not is_public_https_image_url("http://insecure.com/x.jpg")
    assert not is_public_https_image_url("")


def test_consolidate_history_text() -> None:
    out = consolidate_history_text("Intro", ["Cap 1", "Cap 2"], "¿Cuál?")
    assert "Intro" in out
    assert "Cap 1" in out
    assert "¿Cuál?" in out


def test_deliver_bot_response_single_text_without_tag() -> None:
    async def _run() -> None:
        with patch(
            "app.listing_delivery.send_whatsapp_text_message",
            new_callable=AsyncMock,
        ) as mock_text:
            result = await deliver_bot_response(
                access_token="tok",
                phone_number_id="pnid",
                to_wa_id="54911",
                message="Hola, ¿en qué te ayudo?",
                catalog_csv_path=TENANT_RENT,
            )
            mock_text.assert_awaited_once()
            assert result == "Hola, ¿en qué te ayudo?"

    asyncio.run(_run())


def test_deliver_bot_response_multi_image_with_tag() -> None:
    msg = (
        "¡Perfecto! Te comparto opciones:\n\n"
        "[LISTADO:1,8]\n\n"
        "¿Cuál te llama más la atención?"
    )

    async def _run() -> None:
        with (
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
                message=msg,
                catalog_csv_path=TENANT_RENT,
                current_user_text="en en centro, departamento, 2 dormitorios",
                flow_path="alquiler",
            )
            assert mock_text.await_count >= 2
            assert mock_image.await_count == 2
            assert "Opción 1" in result
            assert "¿Cuál te llama" in result

    asyncio.run(_run())
