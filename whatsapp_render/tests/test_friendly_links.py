from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.friendly_links import (
    cta_button_label,
    extract_markdown_links,
    deliver_text_with_friendly_links,
    history_text_for_delivery,
)


def test_extract_markdown_links_removes_urls_from_body() -> None:
    msg = (
        "Acá te dejo la galería 👇\n"
        "[📸 Ver galería de fotos](https://www.instagram.com/p/ABC/)\n\n"
        "Y el video 👇\n"
        "[🎥 Ver video](https://www.instagram.com/reel/XYZ/)"
    )
    cleaned, links = extract_markdown_links(msg)
    assert "instagram.com" not in cleaned
    assert len(links) == 2
    assert links[0][0].startswith("📸")
    assert links[1][0].startswith("🎥")


def test_cta_button_label_truncates_to_20() -> None:
    assert len(cta_button_label("📸 Ver galería de fotos")) <= 20
    assert cta_button_label("📸 Ver galería de fotos") == "📸 Ver galería"


def test_history_text_for_delivery() -> None:
    hist = history_text_for_delivery(
        "Detalle de la propiedad.",
        [("📸 Ver galería", "https://example.com/g")],
    )
    assert "botón enviado" in hist
    assert "example.com" not in hist


def test_deliver_sends_cta_for_markdown_links() -> None:
    msg = (
        "Material visual 👇\n"
        "[📸 Ver galería de fotos](https://example.com/g)\n"
        "[🎥 Ver video](https://example.com/v)"
    )

    async def _run() -> None:
        with (
            patch(
                "app.friendly_links.send_whatsapp_text_message",
                new_callable=AsyncMock,
            ) as mock_text,
            patch(
                "app.friendly_links.send_whatsapp_cta_url_message",
                new_callable=AsyncMock,
            ) as mock_cta,
            patch(
                "app.friendly_links.friendly_cta_links_enabled",
                return_value=True,
            ),
        ):
            out = await deliver_text_with_friendly_links(
                access_token="tok",
                phone_number_id="pnid",
                to_wa_id="54911",
                message=msg,
            )
            mock_text.assert_awaited_once()
            assert mock_cta.await_count == 2
            assert "example.com" not in out
            assert "botón enviado" in out

    asyncio.run(_run())
