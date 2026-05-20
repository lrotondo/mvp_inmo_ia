from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.onboarding.account_update import (
    _extract_account_updates,
    process_account_update_webhook,
)
from app.onboarding.schemas import CompleteOnboardingRequest


def test_onboarding_config_endpoint() -> None:
    with patch.dict(
        os.environ,
        {
            "META_APP_ID": "123456",
            "META_EMBEDDED_SIGNUP_CONFIG_ID": "cfg-99",
            "META_GRAPH_VERSION": "v22.0",
        },
        clear=False,
    ):
        client = TestClient(app)
        res = client.get("/api/onboarding/config")
    assert res.status_code == 200
    data = res.json()
    assert data["app_id"] == "123456"
    assert data["config_id"] == "cfg-99"
    assert data["configured"] is True


def test_complete_requires_auth() -> None:
    with patch.dict(os.environ, {"ONBOARDING_API_SECRET": "secret-test"}, clear=False):
        with patch("app.onboarding.routes.get_engine", return_value=MagicMock()):
            client = TestClient(app)
            res = client.post(
                "/api/onboarding/complete",
                json={
                    "code": "CODE",
                    "waba_id": "111",
                    "phone_number_id": "222",
                },
            )
    assert res.status_code == 401


def test_complete_success() -> None:
    from app.onboarding.schemas import CompleteOnboardingResponse

    fake_result = CompleteOnboardingResponse(
        ok=True,
        tenant_id=7,
        phone_number_id="999",
        waba_id="888",
        display_phone="+54911",
        onboarding_status="connected",
    )

    with patch.dict(os.environ, {"ONBOARDING_API_SECRET": "secret-test"}, clear=False):
        with patch("app.onboarding.routes.get_engine", return_value=MagicMock()):
            with patch(
                "app.onboarding.routes.complete_onboarding",
                new_callable=AsyncMock,
                return_value=fake_result,
            ):
                client = TestClient(app)
                res = client.post(
                    "/api/onboarding/complete",
                    headers={"Authorization": "Bearer secret-test"},
                    json={
                        "code": "SHORT_CODE",
                        "waba_id": "888",
                        "phone_number_id": "999",
                    },
                )
    assert res.status_code == 200
    assert res.json()["tenant_id"] == 7


def test_extract_account_updates() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA123",
                "changes": [
                    {
                        "field": "account_update",
                        "value": {
                            "event": "PARTNER_APP_INSTALLED",
                            "phone_number_id": "PN456",
                        },
                    }
                ],
            }
        ],
    }
    updates = _extract_account_updates(payload)
    assert len(updates) == 1
    assert updates[0]["waba_id"] == "WABA123"
    assert updates[0]["phone_number_id"] == "PN456"


def test_process_account_update_no_db() -> None:
    payload = {
        "entry": [
            {
                "id": "W1",
                "changes": [
                    {
                        "field": "account_update",
                        "value": {"event": "INSTALLED", "phone_number_id": "P1"},
                    }
                ],
            }
        ],
    }
    with patch("app.onboarding.account_update.session_scope") as mock_scope:
        mock_scope.side_effect = RuntimeError("no db")
        count = process_account_update_webhook(payload)
    assert count == 0


def test_complete_onboarding_request_schema() -> None:
    body = CompleteOnboardingRequest(
        code="abc",
        waba_id="1",
        phone_number_id="2",
        pin="123456",
    )
    assert body.pin == "123456"
