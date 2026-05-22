from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.waitlist import WaitlistRequirements, _parse_classifier_json, waitlist_rows_to_csv
from app.models import ClientWaitlist


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
    row = ClientWaitlist(
        phone_number_id="123",
        wa_id="54911",
        contact_name="Test",
        seek_type="venta",
        status="active",
        requirements_json='{"zona":"Centro"}',
        requirements_summary="Centro",
        conversation_summary="Cliente",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    csv_out = waitlist_rows_to_csv([row])
    assert "Centro" in csv_out
    assert "54911" in csv_out


def test_waitlist_export_endpoint_requires_secret() -> None:
    client = TestClient(app)
    with patch.dict(os.environ, {"WAITLIST_EXPORT_SECRET": "test-secret"}, clear=False):
        r = client.get("/admin/waitlist/export.csv?phone_number_id=123")
        assert r.status_code == 401
        r2 = client.get(
            "/admin/waitlist/export.csv?phone_number_id=123",
            headers={"X-Admin-Secret": "test-secret"},
        )
        assert r2.status_code in (200, 503)
