from __future__ import annotations

from app.conversation import HistoryTurn
from app.flow_triggers import (
    apply_visit_handoff,
    filter_alerts_by_real_interest,
    filter_alerts_suppressed_for_browse,
)
from app.lead_context import (
    current_message_is_browse_only,
    extract_property_ref,
    format_user_messages_plain,
    qualifies_for_lead_notification,
    user_declined_zone_preference,
)
from app.leads import LeadClassification


def test_user_declined_zone_blocks_barrio_from_bot_examples() -> None:
    history = [
        HistoryTurn(
            role="assistant",
            content="¿En qué zona? Centro, Villa Italia, Don Bosco...",
        ),
        HistoryTurn(
            role="user",
            content="no tengo zona definida, necesito 2 dormitorios",
        ),
    ]
    ref = extract_property_ref(
        "",
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
        history=history,
        current_user_text="",
        user_only=True,
    )
    assert ref == ""
    assert user_declined_zone_preference(
        format_user_messages_plain(history, ""),
    )


def test_property_ref_from_user_when_specific_address() -> None:
    history = [
        HistoryTurn(
            role="user",
            content="me interesa el de Av. Don Bosco 1800",
        ),
    ]
    ref = extract_property_ref(
        "",
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
        history=history,
        current_user_text="",
        user_only=True,
    )
    assert "Don Bosco" in ref or ref == "4"


def test_filter_drops_visit_alert_without_real_interest() -> None:
    classification = LeadClassification(
        is_real_interest=False,
        property_ref="",
        interest_summary="",
        conversation_summary="",
    )
    filtered = filter_alerts_by_real_interest(
        ["ALERTA_ALQUILER"],
        classification,
    )
    assert filtered == []


def test_filter_keeps_visit_alert_with_real_interest() -> None:
    classification = LeadClassification(
        is_real_interest=True,
        property_ref="ID 3",
        interest_summary="Quiere visitar.",
        conversation_summary="",
    )
    filtered = filter_alerts_by_real_interest(
        ["ALERTA_ALQUILER"],
        classification,
    )
    assert filtered == ["ALERTA_ALQUILER"]


def test_browse_message_does_not_qualify_for_lead() -> None:
    history: list[HistoryTurn] = [
        HistoryTurn(role="user", content="quiero alquilar"),
    ]
    assert current_message_is_browse_only("decime que tenés")
    assert not qualifies_for_lead_notification(
        history,
        "decime que tenés",
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
    )


def test_captacion_alert_not_filtered() -> None:
    filtered = filter_alerts_by_real_interest(
        ["ALERTA_CAPTACION_PROPIETARIO"],
        None,
    )
    assert filtered == ["ALERTA_CAPTACION_PROPIETARIO"]


def test_alquiler_mild_interest_does_not_qualify_for_lead() -> None:
    history: list[HistoryTurn] = [
        HistoryTurn(role="user", content="me interesa la opción 1"),
    ]
    assert not qualifies_for_lead_notification(
        history,
        "me interesa la opción 1",
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
    )


def test_alquiler_visit_request_qualifies_for_lead() -> None:
    history: list[HistoryTurn] = [
        HistoryTurn(role="user", content="quiero visitar el de Don Bosco 1800"),
    ]
    assert qualifies_for_lead_notification(
        history,
        "quiero visitar el de Don Bosco 1800",
        flow_path="alquiler",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
    )


def test_apply_visit_handoff_skips_replacement_for_alquiler() -> None:
    llm_text = "Te cuento más de la opción 2. ¿Querés visitarla?"
    result = apply_visit_handoff(
        llm_text,
        ["ALERTA_ALQUILER"],
        property_ref="ID 6",
        flow_path="alquiler",
    )
    assert result == llm_text


def test_apply_visit_handoff_replaces_for_compra() -> None:
    llm_text = "Genial, coordinamos."
    result = apply_visit_handoff(
        llm_text,
        ["ALERTA_VENTA"],
        property_ref="ID 4",
        flow_path="compra",
        current_user_text="quiero visitar la opción 2",
    )
    assert result != llm_text
    assert "Registré tu interés" in result


def test_apply_visit_handoff_skips_compra_without_current_signal() -> None:
    llm_text = "Te muestro opciones de compra."
    result = apply_visit_handoff(
        llm_text,
        ["ALERTA_VENTA"],
        property_ref="ID 10",
        flow_path="compra",
        current_user_text="que opciones para comprar?",
    )
    assert result == llm_text


def test_cross_flow_alquiler_choice_then_compra_browse_no_qualify() -> None:
    history: list[HistoryTurn] = [
        HistoryTurn(role="user", content="quiero alquilar"),
        HistoryTurn(role="user", content="me gusta la opción 3"),
        HistoryTurn(role="user", content="que opciones para comprar?"),
    ]
    assert current_message_is_browse_only("que opciones para comprar?")
    assert not qualifies_for_lead_notification(
        history,
        "que opciones para comprar?",
        flow_path="compra",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
        flow_just_switched=True,
    )


def test_cross_flow_compra_visit_after_switch_qualifies() -> None:
    history: list[HistoryTurn] = [
        HistoryTurn(role="user", content="me gusta la opción 3"),
        HistoryTurn(role="user", content="que opciones para comprar?"),
        HistoryTurn(role="user", content="quiero visitar la opción 2"),
    ]
    assert qualifies_for_lead_notification(
        history,
        "quiero visitar la opción 2",
        flow_path="compra",
        catalog_sale_path="data/tenants/inmobiliaria_cowork.csv",
        catalog_rent_path="data/tenants/inmobiliaria_cowork_alquiler.csv",
    )


def test_filter_suppresses_venta_alert_on_compra_browse_switch() -> None:
    classification = LeadClassification(
        is_real_interest=True,
        property_ref="ID 10",
        interest_summary="Interesado",
        conversation_summary="",
    )
    filtered = filter_alerts_suppressed_for_browse(
        filter_alerts_by_real_interest(["ALERTA_VENTA"], classification),
        "que opciones para comprar?",
        flow_just_switched=True,
    )
    assert filtered == []
