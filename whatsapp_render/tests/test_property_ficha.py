from __future__ import annotations

from app.property_ficha import build_property_ficha, format_caracteristicas_text


def test_format_caracteristicas_bullets() -> None:
    raw = "Pileta | Jardin | Apto credito"
    text = format_caracteristicas_text(raw)
    assert "Características" in text
    assert "Pileta" in text
    assert "Jardin" in text


def test_build_property_ficha_includes_chars_and_media() -> None:
    row = {
        "Direccion": "Av. Test 100",
        "Barrio": "Centro",
        "Precio": "100000",
        "Ambientes": "3",
        "Caracteristicas": "Casa | Pileta | Garage",
        "url_link_fotos": "https://example.com/g",
        "url_link_video": "https://example.com/v",
    }
    ficha = build_property_ficha(row, include_media_links=True)
    assert "Av. Test" in ficha
    assert "Pileta" in ficha
    assert "Ver galería" in ficha
    assert "Ver video" in ficha


def test_build_listing_caption_style_without_media_links() -> None:
    row = {
        "Direccion": "Don Bosco 1800",
        "Barrio": "Don Bosco",
        "Precio": "380000",
        "Ambientes": "4",
        "Caracteristicas": "Zona residencial | Pileta",
        "foto_principal": "https://example.com/p.jpg",
    }
    ficha = build_property_ficha(row, include_media_links=False, option_index=1)
    assert "Opción 1" in ficha
    assert "Pileta" in ficha
    assert "Ver galería" not in ficha
