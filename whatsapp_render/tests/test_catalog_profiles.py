"""Perfiles de catálogo compacto: venta vs alquiler."""

from __future__ import annotations

import unittest

from app.catalog import get_catalog_for_flow
from app.catalog_profiles import (
    format_catalog_compact_for_branch,
    format_rent_compact,
    format_sale_compact,
)


class TestCatalogProfiles(unittest.TestCase):
    def test_sale_row_uses_lugar_zona_not_barrio(self) -> None:
        row = {
            "ID": "1",
            "Titulo": "Casa amplia",
            "Tipo": "Casa",
            "Direccion": "Av. Brasil 100",
            "Lugar": "Tandil",
            "Zona": "Avda Brasil",
            "Barrio": "NoDebeAparecer",
            "Precio": "US$200,000",
            "Dormitorios": "3",
            "Ambientes": "4",
            "Caracteristicas": "Patio",
        }
        text = format_sale_compact([row])
        self.assertIn("Lugar: Tandil", text)
        self.assertIn("Zona: Avda Brasil", text)
        self.assertIn("Precio USD", text)
        self.assertNotIn("Barrio", text)
        self.assertNotIn("NoDebeAparecer", text)

    def test_rent_row_includes_expensas_not_sale_fields(self) -> None:
        row = {
            "ID": "9",
            "Titulo": "Depto centro",
            "Tipo": "Departamento",
            "Direccion": "Chacabuco 500",
            "Barrio": "Centro",
            "Lugar": "Ignorado",
            "Zona": "Ignorado",
            "Precio": "450000",
            "Expensas": "85000",
            "Dormitorios": "2",
            "Ambientes": "2",
            "Caracteristicas": "Luminoso",
            "foto_principal": "https://example.com/p.jpg",
        }
        text = format_rent_compact([row])
        self.assertIn("Barrio: Centro", text)
        self.assertIn("Expensas ARS: 85000", text)
        self.assertIn("Precio mensual ARS", text)
        self.assertNotIn("Lugar:", text)
        self.assertNotIn("Zona:", text)
        self.assertNotIn("Precio USD", text)

    def test_rent_media_flags_without_urls(self) -> None:
        row = {
            "ID": "9",
            "Direccion": "Test",
            "Barrio": "Centro",
            "Precio": "100",
            "foto_principal": "https://example.com/f",
            "url_link_fotos": "https://example.com/g",
            "url_link_video": "https://example.com/v",
        }
        text = format_catalog_compact_for_branch([row], "alquiler")
        self.assertIn("media: tiene_foto", text)
        self.assertNotIn("https://example.com", text)

    def test_get_catalog_for_flow_branches_differ(self) -> None:
        sale_path = "data/tenants/inmobiliaria_cowork.csv"
        rent_path = "data/tenants/inmobiliaria_cowork_alquiler.csv"
        _, sale_block, _ = get_catalog_for_flow(
            "compra", catalog_sale_path=sale_path, catalog_rent_path=rent_path
        )
        _, rent_block, _ = get_catalog_for_flow(
            "alquiler", catalog_sale_path=sale_path, catalog_rent_path=rent_path
        )
        self.assertTrue(sale_block.strip())
        self.assertTrue(rent_block.strip())
        if "Zona:" in sale_block or "Lugar:" in sale_block:
            self.assertNotIn("Precio mensual ARS", sale_block)
        if rent_block.strip() and rent_block != "(catálogo vacío o no disponible.)":
            self.assertNotIn("Precio USD", rent_block.split("\n")[0])


if __name__ == "__main__":
    unittest.main()
