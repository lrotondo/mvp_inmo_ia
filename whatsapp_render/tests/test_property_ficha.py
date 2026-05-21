from __future__ import annotations

from app.property_ficha import (
    build_detail_media_links_block,
    build_property_ficha,
    format_caracteristicas_text,
)


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
    assert "Foto" in ficha or "Fotos" in ficha
    assert "Video" in ficha


def test_detail_media_links_primary_before_instagram() -> None:
    row = {
        "foto_principal": "https://images.wasi.co/inmuebles/photo.jpg",
        "url_link_fotos": "https://www.instagram.com/p/ABC123/",
    }
    block = build_detail_media_links_block(row)
    assert "Fotos](https://images.wasi.co" in block
    assert "instagram.com/p/ABC123" in block
    foto_idx = block.index("Fotos")
    ig_idx = block.index("instagram.com")
    assert foto_idx < ig_idx


def test_format_caracteristicas_strips_instagram_bullet() -> None:
    raw = "Pileta | Ver https://instagram.com/p/xyz | Garage"
    text = format_caracteristicas_text(raw)
    assert "Pileta" in text
    assert "Garage" in text
    assert "instagram" not in text.lower()


def test_build_property_ficha_uses_titulo_and_dormitorios() -> None:
    row = {
        "Titulo": "Casa con pileta",
        "Direccion": "Av. Test 100",
        "Barrio": "Centro",
        "Precio": "100000",
        "Dormitorios": "3",
        "Ambientes": "4 ambientes",
        "Caracteristicas": "Pileta",
    }
    ficha = build_property_ficha(row, include_media_links=False)
    assert "Casa con pileta" in ficha
    assert "3 dormitorios" in ficha
    assert "Av. Test 100" in ficha


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
