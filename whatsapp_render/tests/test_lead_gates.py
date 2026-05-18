from __future__ import annotations

from app.conversation import HistoryTurn
from app.flow_triggers import filter_alerts_by_real_interest
from app.lead_context import (
    extract_property_ref,
    format_user_messages_plain,
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


def test_captacion_alert_not_filtered() -> None:
    filtered = filter_alerts_by_real_interest(
        ["ALERTA_CAPTACION_PROPIETARIO"],
        None,
    )
    assert filtered == ["ALERTA_CAPTACION_PROPIETARIO"]
