from __future__ import annotations

import unittest

from app.catalog import (
    _media_suffix_parts,
    format_catalog_compact,
    is_property_available,
    load_properties_for_catalog_path,
)
from app.catalog_sources import rows_from_csv_text


class TestIsPropertyAvailable(unittest.TestCase):
    def test_affirmative_values(self) -> None:
        for value in ("si", "sí", "S", "1", "true", "yes", "disponible", "x"):
            self.assertTrue(
                is_property_available({"Disponible": value}),
                msg=value,
            )

    def test_hidden_values(self) -> None:
        for value in ("", "no", "0", "false", "reservado"):
            self.assertFalse(
                is_property_available({"Disponible": value}),
                msg=repr(value),
            )

    def test_missing_column_is_hidden(self) -> None:
        self.assertFalse(is_property_available({"ID": "1"}))


class TestCatalogAvailabilityFilter(unittest.TestCase):
    def test_load_filters_by_disponible(self) -> None:
        csv_text = (
            "ID,Direccion,Barrio,Precio,Ambientes,Caracteristicas,Disponible,Link_Fotos\n"
            "1,Calle A,Centro,100,2,,-,https://example.com/a\n"
            "2,Calle B,Centro,200,3,,si,https://example.com/b\n"
            "3,Calle C,Centro,300,4,,no,https://example.com/c\n"
        )
        rows = rows_from_csv_text(csv_text)
        available = [r for r in rows if is_property_available(r)]
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0]["ID"], "2")


class TestMediaSuffixParts(unittest.TestCase):
    def test_includes_galeria_and_video_when_present(self) -> None:
        row = {
            "Link_Fotos": "https://example.com/thumb",
            "url_link_fotos": "https://example.com/galeria",
            "url_link_video": "https://example.com/video",
            "Tour_360": "https://example.com/tour",
        }
        suffix = _media_suffix_parts(row)
        self.assertIn("Fotos: https://example.com/thumb", suffix)
        self.assertIn("Galeria: https://example.com/galeria", suffix)
        self.assertIn("Video: https://example.com/video", suffix)
        self.assertIn("Tour_360: https://example.com/tour", suffix)

    def test_omits_empty_media_fields(self) -> None:
        suffix = _media_suffix_parts({"Link_Fotos": "https://example.com/thumb"})
        self.assertIn("Fotos:", suffix)
        self.assertNotIn("Galeria:", suffix)
        self.assertNotIn("Video:", suffix)


class TestFormatCatalogCompact(unittest.TestCase):
    def test_compact_line_includes_galeria_and_video(self) -> None:
        row = {
            "ID": "9",
            "Direccion": "Test 1",
            "Barrio": "Centro",
            "Precio": "100",
            "Ambientes": "2",
            "Caracteristicas": "Luminoso",
            "Link_Fotos": "https://example.com/f",
            "url_link_fotos": "https://example.com/galeria",
            "url_link_video": "https://example.com/video",
        }
        text = format_catalog_compact([row])
        self.assertIn("Galeria: https://example.com/galeria", text)
        self.assertIn("Video: https://example.com/video", text)


class TestHeaderAliases(unittest.TestCase):
    def test_url_link_fotos_header_normalized(self) -> None:
        csv_text = (
            "ID,Direccion,Barrio,Precio,Ambientes,Caracteristicas,disponible,"
            "url_link_fotos,url_link_video\n"
            "1,Calle 1,Centro,100,2,,si,https://example.com/g,https://example.com/v\n"
        )
        rows = rows_from_csv_text(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url_link_fotos"], "https://example.com/g")
        self.assertEqual(rows[0]["url_link_video"], "https://example.com/v")
        self.assertEqual(rows[0]["Disponible"], "si")


class TestLoadPropertiesIntegration(unittest.TestCase):
    def test_load_from_inline_csv_via_temp_path(self) -> None:
        # Uses rows_from_csv_text logic indirectly through filter helper
        rows = rows_from_csv_text(
            "ID,Disponible\n1,si\n2,\n3,no\n"
        )
        filtered = [r for r in rows if is_property_available(r)]
        self.assertEqual([r["ID"] for r in filtered], ["1"])

    def test_default_tenant_csv_returns_list(self) -> None:
        props = load_properties_for_catalog_path(
            "data/tenants/inmobiliaria_cowork_alquiler.csv"
        )
        self.assertIsInstance(props, list)


if __name__ == "__main__":
    unittest.main()
