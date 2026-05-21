from __future__ import annotations

from app.property_ficha import (
    build_detail_media_links_block,
    build_property_ficha,
    format_caracteristicas_text,
    replace_markdown_links_with_labels,
)


def test_replace_markdown_links_keeps_icon_label_only() -> None:
    raw = "[📸 Fotos](https://cdn.example.com/very/long/path.jpg?token=abc)"
    out = replace_markdown_links_with_labels(raw)
    assert out == "📸 Fotos"
    assert "https://" not in out
    assert "[" not in out


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
    assert "material visual" in ficha.lower()
    assert "http" not in ficha


def test_media_buttons_primary_and_instagram() -> None:
    from app.property_ficha import collect_media_link_buttons

    row = {
        "foto_principal": "https://images.wasi.co/inmuebles/photo.jpg",
        "url_link_fotos": "https://www.instagram.com/p/ABC123/",
    }
    buttons = collect_media_link_buttons(row)
    urls = [b.url for b in buttons]
    assert any("instagram.com" in u for u in urls)
    assert "images.wasi.co" not in " ".join(urls) or len(urls) == 1
    assert build_detail_media_links_block(row)
    assert "http" not in build_detail_media_links_block(row)


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
