from app.conversation import HistoryTurn
from app.search_profile import build_search_profile


def test_alquiler_casa_sin_zona_incomplete_then_complete():
    history = [
        HistoryTurn(role="user", content="quiero alquilar"),
        HistoryTurn(role="assistant", content="¿casa o departamento?"),
        HistoryTurn(role="user", content="casa 2 o 3 dormitorios"),
    ]
    profile = build_search_profile(history, "zonas preferidas", "alquiler")
    assert profile.property_type == "casa"
    assert "zona" in profile.missing_fields

    history2 = history + [
        HistoryTurn(role="user", content="sin preferencia de zona"),
    ]
    profile2 = build_search_profile(history2, "ver ideas", "alquiler")
    assert profile2.is_complete
    assert profile2.any_zone


def test_compra_requires_presupuesto():
    history = [
        HistoryTurn(role="user", content="busco comprar casa en centro"),
        HistoryTurn(role="user", content="3 dormitorios"),
    ]
    profile = build_search_profile(history, "", "compra")
    assert "presupuesto" in profile.missing_fields
