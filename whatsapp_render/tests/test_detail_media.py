from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.catalog import get_property_row_by_ref, load_properties_for_catalog_path
from app.conversation import HistoryTurn
from app.detail_media import (
    bot_promises_visual_material,
    enrich_detail_media_from_catalog,
    property_ref_for_detail_enrich,
    should_enrich_property_detail,
    strip_property_media_from_message,
    user_requests_property_detail,
)
from app.lead_context import extract_property_ref
from app.property_ficha import build_detail_media_links_block
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
    "Link_Fotos": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800",
}


def test_tenant_catalog_loads_without_disponible_column() -> None:
    rows = load_properties_for_catalog_path(TENANT_RENT)
    assert len(rows) >= 5


def test_extract_property_ref_arana_from_user_text() -> None:
    ref = extract_property_ref(
        "",
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path=TENANT_RENT,
        history=[],
        current_user_text="dale quiero mas info del arana al 200",
        user_only=True,
    )
    assert ref
    row = get_property_row_by_ref(TENANT_RENT, ref)
    assert row is not None
    assert "Arana" in str(row.get("Direccion", ""))


def test_property_ref_from_history_when_user_asks_fotos() -> None:
    history = [
        HistoryTurn(role="user", content="mas info del arana 200"),
    ]
    ref = property_ref_for_detail_enrich(
        current_user_text="fotos o videos?",
        outbound_message="Te paso el material visual",
        history=history,
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path=TENANT_RENT,
        catalog_csv_path=TENANT_RENT,
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
            history=[
                HistoryTurn(role="user", content="info del arana 200"),
            ],
        )
    assert "Ver galería" in out or "Ver fotos" in out
    assert "Características" in out


def test_user_requests_fotos_detected() -> None:
    assert user_requests_property_detail("fotos o videos?")


def test_bot_promises_galeria_comparto() -> None:
    assert bot_promises_visual_material(
        "Ahora te comparto la galería completa de la propiedad de Arana 200 👇"
    )


def test_try_deliver_sends_text_with_links_when_enriched() -> None:
    from app.detail_media import try_deliver_single_property_visual

    enriched = (
        "Disculpá.\n\n"
        "*Características:*\n• Patio\n"
        "¡Genial! Te dejo la galería completa 👇\n"
        "[📸 Ver galería de fotos](https://example.com/g)\n\n"
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
                history=[
                    HistoryTurn(role="user", content="arana 200"),
                ],
                catalog_sale_path=None,
                catalog_rent_path=TENANT_RENT,
                property_ref="5",
            )
            assert result is not None
            assert "galería" in result.lower() or "Ver" in result
            assert mock_img.await_count + mock_txt.await_count >= 1

    asyncio.run(_run())


def test_build_detail_media_links_uses_primary_photo() -> None:
    block = build_detail_media_links_block(FAKE_ROW)
    assert "Ver galería" in block or "Ver fotos" in block
    assert "unsplash" in block or "example" in block
