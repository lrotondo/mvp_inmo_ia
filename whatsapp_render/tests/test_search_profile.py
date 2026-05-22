from app.capture_flow import append_user_flow_message
from app.search_profile import build_search_profile


def test_alquiler_casa_sin_zona_incomplete_then_complete() -> None:
    capture = append_user_flow_message({}, "alquiler", "quiero alquilar")
    capture = append_user_flow_message(capture, "alquiler", "casa 2 o 3 dormitorios")
    profile = build_search_profile(capture, "zonas preferidas", "alquiler")
    assert profile.property_type == "casa"
    assert "zona" in profile.missing_fields

    capture = append_user_flow_message(capture, "alquiler", "sin preferencia de zona")
    profile2 = build_search_profile(capture, "ver ideas", "alquiler")
    assert profile2.is_complete
    assert profile2.any_zone


def test_compra_requires_presupuesto() -> None:
    capture = append_user_flow_message({}, "compra", "busco comprar casa en centro")
    capture = append_user_flow_message(capture, "compra", "3 dormitorios")
    profile = build_search_profile(capture, "", "compra")
    assert "presupuesto" in profile.missing_fields
