from __future__ import annotations

from app.catalog_display import (
    format_ficha_ambientes,
    format_ficha_dormitorios,
    format_ficha_precio,
)
from app.property_ficha import build_property_ficha, build_property_header_lines


def test_format_precio_consultar() -> None:
    assert format_ficha_precio("Consultar", branch="compra") == "Consultar precio"
    assert format_ficha_precio("A consultar", branch="compra") == "Consultar precio"


def test_format_precio_usd_variants() -> None:
    assert format_ficha_precio("USD 300000", branch="compra") == "Precio: 300.000 dólares"
    assert format_ficha_precio("US$300,000", branch="compra") == "Precio: 300.000 dólares"
    assert format_ficha_precio("US$350,000", branch="compra") == "Precio: 350.000 dólares"


def test_format_precio_no_usd_label_or_double_prefix() -> None:
    line = format_ficha_precio("USD 300000", branch="compra")
    assert "Precio USD" not in line
    assert "$USD" not in line


def test_format_dormitorios_singular_plural() -> None:
    assert format_ficha_dormitorios("1") == "1 dormitorio"
    assert format_ficha_dormitorios("3") == "3 dormitorios"
    assert format_ficha_dormitorios("1 dormitorios") == "1 dormitorio"


def test_format_ambientes_singular_plural() -> None:
    assert format_ficha_ambientes("1") == "1 ambiente"
    assert format_ficha_ambientes("4 ambientes") == "4 ambientes"
    assert format_ficha_ambientes("1 ambientes") == "1 ambiente"


def test_format_habitacion_in_dormitorios_field() -> None:
    assert format_ficha_dormitorios("1 habitación") == "1 habitación"
    assert format_ficha_dormitorios("2 habitaciones") == "2 habitaciones"


def test_build_property_header_lines_ficha_integration() -> None:
    row = {
        "Titulo": "Depto centro",
        "Direccion": "Giaconi 1400",
        "Barrio": "Semicentro",
        "Precio": "Consultar",
        "Dormitorios": "1",
        "Ambientes": "1 ambientes",
    }
    lines = build_property_header_lines(row, branch="alquiler")
    assert lines[0] == "*Giaconi 1400*"
    assert "Depto centro" in lines[1]
    assert "Consultar precio" in lines[1]
    assert "$Consultar" not in "\n".join(lines)
    assert "1 dormitorio" in lines[1]
    assert "1 ambiente" not in lines[1]
    assert "1 dormitorios" not in "\n".join(lines)


def test_build_property_header_lines_listing_fontana() -> None:
    row = {
        "Titulo": "Hermosa casa en alquiler, espacios comodos y super luminosos",
        "Direccion": "Fontana al 2500",
        "Barrio": "Fontana al 2500",
        "Precio": "1800000",
        "Dormitorios": "3",
        "Ambientes": "3",
    }
    lines = build_property_header_lines(row, option_index=2, branch="alquiler")
    assert lines[0] == "*Opción 2, Fontana al 2500*"
    assert "Hermosa casa" in lines[1]
    assert "3 dormitorios" in lines[1]
    assert "3 ambientes" not in lines[1]
    assert "Fontana al 2500, Fontana" not in "\n".join(lines)


def test_build_property_ficha_usd_sale() -> None:
    row = {
        "Titulo": "Casa Los Ombúes",
        "Direccion": "Los Ombúes",
        "Zona": "Country",
        "Precio": "US$298,000",
        "Dormitorios": "3",
        "Ambientes": "3 ambientes",
        "Caracteristicas": "Pileta",
    }
    ficha = build_property_ficha(row, include_media_links=False, branch="compra")
    assert "Precio: 298.000 dólares" in ficha
    assert "Precio USD" not in ficha
    assert "3 dormitorios" in ficha
