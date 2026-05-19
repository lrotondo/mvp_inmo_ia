from __future__ import annotations

import json
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.conversation import HistoryTurn
from app.flow_triggers import filter_waitlist_tag, parse_flow_alerts
from app.main import app
from app.waitlist import WaitlistRequirements, _parse_classifier_json, waitlist_rows_to_csv
from app.waitlist_context import (
    bot_recently_prompted_waitlist_confirm,
    qualifies_for_waitlist_registration,
    should_register_waitlist,
    user_accepts_waitlist,
    user_declines_waitlist,
    user_signals_no_fit,
)
from app.models import ClientWaitlist


def test_user_signals_no_fit() -> None:
    assert user_signals_no_fit("ninguna me convence")
    assert not user_signals_no_fit("quiero visitar")


def test_user_accepts_waitlist() -> None:
    assert user_accepts_waitlist("sí, avisame cuando haya algo")
    assert user_accepts_waitlist("dale, registrame")
    assert user_accepts_waitlist("está perfecto, muchas gracias")
    assert user_accepts_waitlist("confirmo, así está bien")
    assert not user_accepts_waitlist("no gracias")
    assert not user_declines_waitlist("sí dale")


def test_qualifies_requires_explicit_accept() -> None:
    assert qualifies_for_waitlist_registration("sí, quiero que me avisen")
    assert qualifies_for_waitlist_registration("está perfecto, muchas gracias")
    assert not qualifies_for_waitlist_registration("ninguna me sirve")


def test_parse_flow_alerts_strips_waitlist_tag() -> None:
    text = "Quedaste registrado.\n[LISTA_ESPERA]\n"
    clean, alerts, has_waitlist = parse_flow_alerts(text)
    assert has_waitlist is True
    assert "[LISTA_ESPERA]" not in clean
    assert alerts == []


def test_filter_waitlist_tag_requires_accept() -> None:
    assert filter_waitlist_tag(True, "sí, avisame")
    assert filter_waitlist_tag(True, "está perfecto, muchas gracias")
    assert not filter_waitlist_tag(True, "ninguna me convence")
    assert not filter_waitlist_tag(False, "sí, avisame")


def test_filter_waitlist_tag_backup_without_tag() -> None:
    history = [
        HistoryTurn(
            role="assistant",
            content="¿Confirmás que está bien así? Te sumo a la lista de espera.",
        ),
    ]
    assert filter_waitlist_tag(
        False,
        "está perfecto, muchas gracias",
        history=history,
    )
    assert not filter_waitlist_tag(
        False,
        "está perfecto, muchas gracias",
        history=[],
    )


def test_should_register_waitlist_tag_without_strict_accept() -> None:
    assert should_register_waitlist(True, "ok, gracias")
    assert should_register_waitlist(
        True,
        "está perfecto, muchas gracias",
    )
    assert not should_register_waitlist(True, "no gracias")


def test_bot_recently_prompted_waitlist_confirm() -> None:
    history = [
        HistoryTurn(role="user", content="ninguna me convence"),
        HistoryTurn(
            role="assistant",
            content="¿Confirmás que está bien este resumen para la lista de espera?",
        ),
    ]
    assert bot_recently_prompted_waitlist_confirm(history)


def test_parse_classifier_json() -> None:
    raw = json.dumps(
        {
            "zona": "Centro",
            "presupuesto": "USD 200000",
            "ambientes": "3",
            "preferencias": "con garage",
            "notas": "",
            "requirements_summary": "Busca depto 3 amb en Centro.",
            "conversation_summary": "Cliente en compra sin match en catálogo.",
        }
    )
    parsed = _parse_classifier_json(raw)
    assert parsed is not None
    assert parsed.zona == "Centro"
    assert "depto" in parsed.requirements_summary


def test_waitlist_rows_to_csv() -> None:
    from datetime import datetime, timezone

    row = ClientWaitlist(
        phone_number_id="123",
        wa_id="54911",
        contact_name="Test",
        seek_type="venta",
        status="active",
        requirements_json='{"zona":"Centro"}',
        requirements_summary="Centro, 3 amb",
        conversation_summary="Resumen",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    csv_out = waitlist_rows_to_csv([row])
    assert "Centro, 3 amb" in csv_out
    assert "venta" in csv_out


def test_export_endpoint_unauthorized() -> None:
    client = TestClient(app)
    with patch.dict(os.environ, {"WAITLIST_EXPORT_SECRET": "secret123"}, clear=False):
        r = client.get(
            "/admin/waitlist/export.csv",
            params={"phone_number_id": "123"},
        )
    assert r.status_code == 401


def test_export_endpoint_no_secret_configured() -> None:
    client = TestClient(app)
    env = {k: v for k, v in os.environ.items() if k != "WAITLIST_EXPORT_SECRET"}
    with patch.dict(os.environ, env, clear=True):
        r = client.get(
            "/admin/waitlist/export.csv",
            params={"phone_number_id": "123"},
            headers={"X-Admin-Secret": "x"},
        )
    assert r.status_code == 503
