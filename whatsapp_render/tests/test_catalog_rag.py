from pathlib import Path

from app.catalog_rag import index_catalog, search_catalog_ids

_RENT_CSV = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "tenants"
    / "inmobiliaria_cowork_alquiler.csv"
)


def test_rag_centro_finds_rows():
    path = str(_RENT_CSV)
    index_catalog(path, "alquiler")
    ids = search_catalog_ids(path, "alquiler", "casa cerca del centro", k=5)
    assert ids
