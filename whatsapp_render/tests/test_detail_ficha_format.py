from __future__ import annotations

from app.property_ficha import (
    build_detail_delivery_caption,
    compact_detail_intro_for_row,
    extract_detail_tail,
)

OMBUES_ROW = {
    "ID": "1",
    "Titulo": "Casa en Los Ombúes y Los Tilos",
    "Direccion": "Los Ombúes y Los Tilos",
    "Barrio": "Country",
    "Precio": "300000",
    "Dormitorios": "3",
    "Ambientes": "4 ambientes",
    "Caracteristicas": "Piscina | Galería con parrilla | Losa radiante",
    "foto_principal": "https://images.wasi.co/inmuebles/photo.jpg",
    "url_link_fotos": "https://www.instagram.com/p/album123/",
    "url_link_video": "https://www.instagram.com/reel/VID/",
}


def test_compact_intro_strips_llm_essay() -> None:
    intro = (
        "¡Excelente elección! La propiedad de *Los Ombúes y Los Tilos* es una casa completa.\n\n"
        "Te cuento: tiene *3 dormitorios*, living comedor, piscina. "
        "El precio es de *USD 300.000*.\n\n"
        "Acá te paso el material visual 👇"
    )
    compact = compact_detail_intro_for_row(intro, OMBUES_ROW, None)
    assert "dormitorio" not in compact.lower()
    assert "300.000" not in compact
    assert "material visual" not in compact.lower()
    assert "ombúes" in compact.lower() or "Excelente" in compact


def test_detail_caption_uses_catalog_not_llm_essay() -> None:
    body = (
        "¡Excelente elección! La propiedad de *Los Ombúes y Los Tilos* es una casa completa.\n\n"
        "Te cuento: tiene *3 dormitorios*, living comedor, piscina. "
        "El precio es de *USD 300.000*.\n\n"
        "Acá te paso el material visual 👇\n\n"
        "¿Te gustaría coordinar una visita?"
    )
    intro = body.split("¿Te")[0]
    tail = extract_detail_tail(body)
    caption = build_detail_delivery_caption(
        OMBUES_ROW,
        intro=intro,
        tail=tail,
    )
    assert "Piscina" in caption
    assert "Los Ombúes" in caption
    assert "living comedor" not in caption.lower()
    assert "¿Te gustaría coordinar" in caption
    assert "material visual" not in caption.lower()
