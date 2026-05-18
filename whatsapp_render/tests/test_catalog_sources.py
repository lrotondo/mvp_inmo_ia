from __future__ import annotations

import unittest
from unittest.mock import patch

from app.catalog import _load_rows, get_cached_compact_catalog
from app.catalog_sources import (
    CatalogRef,
    is_google_sheet_ref,
    parse_catalog_ref,
    rows_from_sheet_values,
)


class TestParseCatalogRef(unittest.TestCase):
    def test_google_sheet_url(self) -> None:
        url = "https://docs.google.com/spreadsheets/d/abc123XYZ_-/edit#gid=0"
        ref = parse_catalog_ref(url)
        assert ref is not None
        self.assertEqual(ref.kind, "google_sheet")
        self.assertEqual(ref.spreadsheet_id, "abc123XYZ_-")

    def test_google_sheet_id_only(self) -> None:
        ref = parse_catalog_ref("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")
        assert ref is not None
        self.assertEqual(ref.kind, "google_sheet")

    def test_csv_path(self) -> None:
        ref = parse_catalog_ref("data/tenants/inmobiliaria_cowork.csv")
        assert ref is not None
        self.assertEqual(ref.kind, "csv")

    def test_is_google_sheet_ref(self) -> None:
        self.assertTrue(is_google_sheet_ref("https://docs.google.com/spreadsheets/d/abc/edit"))
        self.assertFalse(is_google_sheet_ref("data/tenants/foo.csv"))


class TestRowsFromSheetValues(unittest.TestCase):
    def test_parses_header_and_rows(self) -> None:
        values = [
            ["ID", "Direccion", "Barrio", "Precio"],
            ["1", "Calle 1", "Centro", "100000"],
            ["", "", "", ""],
        ]
        rows = rows_from_sheet_values(values)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ID"], "1")
        self.assertEqual(rows[0]["Barrio"], "Centro")


class TestCatalogCache(unittest.TestCase):
    def test_google_sheet_ttl_cache(self) -> None:
        ref = CatalogRef(
            kind="google_sheet",
            raw="abc123XYZ_-abcdefghijklmnop",
            spreadsheet_id="abc123XYZ_-abcdefghijklmnop",
        )
        call_count = 0

        def fake_fetch(r: CatalogRef) -> list[dict]:
            nonlocal call_count
            call_count += 1
            return [{"ID": "1", "Direccion": "X", "Barrio": "Y", "Precio": "1"}]

        with patch("app.catalog.fetch_rows", side_effect=fake_fetch):
            with patch.dict("os.environ", {"CATALOG_CACHE_TTL_SECONDS": "60"}):
                from app import catalog as catalog_mod

                catalog_mod._rows_cache.clear()
                _load_rows(ref)
                _load_rows(ref)
                self.assertEqual(call_count, 1)

    def test_csv_local_loads(self) -> None:
        count, block = get_cached_compact_catalog(
            "data/tenants/inmobiliaria_cowork_alquiler.csv"
        )
        self.assertGreaterEqual(count, 0)
        self.assertIsInstance(block, str)


if __name__ == "__main__":
    unittest.main()
