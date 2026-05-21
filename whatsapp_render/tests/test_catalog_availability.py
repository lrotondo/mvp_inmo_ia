from __future__ import annotations

import unittest

from app.catalog import (
    _media_suffix_parts,
    format_catalog_compact,
    gallery_photo_url,
    is_property_available,
    load_properties_for_catalog_path,
    primary_photo_url,
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
            "ID,Direccion,Barrio,Precio,Ambientes,Caracteristicas,Disponible,foto_principal\n"
            "1,Calle A,Centro,100,2,,-,https://example.com/a\n"
            "2,Calle B,Centro,200,3,,si,https://example.com/b\n"
            "3,Calle C,Centro,300,4,,no,https://example.com/c\n"
        )
        rows = rows_from_csv_text(csv_text)
        available = [r for r in rows if is_property_available(r)]
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0]["ID"], "2")


class TestPhotoUrlHelpers(unittest.TestCase):
    def test_primary_photo_prefers_foto_principal(self) -> None:
        row = {
            "foto_principal": "https://example.com/principal",
            "Link_Fotos": "https://example.com/legacy",
        }
        self.assertEqual(primary_photo_url(row), "https://example.com/principal")
        self.assertEqual(
            primary_photo_url({"Link_Fotos": "https://example.com/legacy"}),
            "https://example.com/legacy",
        )

    def test_gallery_photo_url(self) -> None:
        self.assertEqual(
            gallery_photo_url({"url_link_fotos": "https://example.com/galeria"}),
            "https://example.com/galeria",
        )


class TestMediaSuffixParts(unittest.TestCase):
    def test_includes_galeria_and_video_when_present(self) -> None:
        row = {
            "foto_principal": "https://example.com/thumb",
            "url_link_fotos": "https://example.com/galeria",
            "url_link_video": "https://example.com/video",
            "Tour_360": "https://example.com/tour",
        }
        suffix = _media_suffix_parts(row)
        self.assertIn("foto_principal: https://example.com/thumb", suffix)
        self.assertIn("url_link_fotos: https://example.com/galeria", suffix)
        self.assertIn("Video: https://example.com/video", suffix)
        self.assertIn("Tour_360: https://example.com/tour", suffix)

    def test_omits_empty_media_fields(self) -> None:
        suffix = _media_suffix_parts({"foto_principal": "https://example.com/thumb"})
        self.assertIn("foto_principal:", suffix)
        self.assertNotIn("url_link_fotos:", suffix)
        self.assertNotIn("Video:", suffix)


class TestFormatCatalogCompact(unittest.TestCase):
    def test_compact_line_includes_titulo_and_dormitorios(self) -> None:
        row = {
            "ID": "9",
            "Titulo": "Depto luminoso",
            "Direccion": "Test 1",
            "Barrio": "Centro",
            "Precio": "100",
            "Dormitorios": "2",
            "Ambientes": "2 ambientes",
            "Caracteristicas": "Luminoso",
        }
        text = format_catalog_compact([row])
        self.assertIn("Depto luminoso", text)
        self.assertIn("Dormitorios: 2", text)

    def test_compact_line_includes_galeria_and_video(self) -> None:
        row = {
            "ID": "9",
            "Direccion": "Test 1",
            "Barrio": "Centro",
            "Precio": "100",
            "Ambientes": "2",
            "Caracteristicas": "Luminoso",
            "foto_principal": "https://example.com/f",
            "url_link_fotos": "https://example.com/galeria",
            "url_link_video": "https://example.com/video",
        }
        text = format_catalog_compact([row])
        self.assertIn("url_link_fotos: https://example.com/galeria", text)
        self.assertIn("Video: https://example.com/video", text)


class TestHeaderAliases(unittest.TestCase):
    def test_titulo_and_dormitorios_headers(self) -> None:
        rows = rows_from_csv_text(
            "ID,Titulo,Direccion,Barrio,Precio,Dormitorios,Ambientes,Caracteristicas,disponible\n"
            "1,Casa 3 dorm,Av. Test 1,Centro,100,3,3 ambientes,Luminoso,si\n"
        )
        self.assertEqual(rows[0]["Titulo"], "Casa 3 dorm")
        self.assertEqual(rows[0]["Dormitorios"], "3")

    def test_foto_principal_header(self) -> None:
        rows = rows_from_csv_text(
            "ID,Direccion,Barrio,Precio,Ambientes,Caracteristicas,disponible,foto_principal\n"
            "1,Calle 1,Centro,100,2,,si,https://example.com/principal\n"
        )
        self.assertEqual(rows[0]["foto_principal"], "https://example.com/principal")

    def test_link_fotos_legacy_header_maps_to_foto_principal(self) -> None:
        rows = rows_from_csv_text(
            "ID,Direccion,Barrio,Precio,Ambientes,Caracteristicas,disponible,Link_Fotos\n"
            "2,Calle 2,Centro,100,2,,si,https://example.com/legacy\n"
        )
        self.assertEqual(rows[0]["foto_principal"], "https://example.com/legacy")

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
