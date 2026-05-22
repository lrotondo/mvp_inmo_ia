from __future__ import annotations

import asyncio

from app.turn_handler import build_detail_outbound
from tests.test_listing_context import MOCK_ROWS


def test_detail_outbound_photos_not_excelente_eleccion() -> None:
    text = asyncio.run(
        build_detail_outbound(
            "tenes mas fotos de la segunda?",
            listing_rows=MOCK_ROWS,
        )
    )
    assert "Excelente elección" not in text
    assert "fotos" in text.lower()
    assert "Sarmiento" in text or "detalle" in text.lower()
