from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.meta_graph import pick_default_phone_number_id
from app.onboarding.account_update import (
    _extract_account_updates,
    normalize_account_update_fields,
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


def test_complete_without_phone_id_in_body() -> None:
    from app.onboarding.schemas import CompleteOnboardingResponse

    fake_result = CompleteOnboardingResponse(
        ok=True,
        tenant_id=8,
        phone_number_id="777",
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
                    },
                )
    assert res.status_code == 200
    assert res.json()["phone_number_id"] == "777"


def test_extract_account_updates_legacy_flat() -> None:
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
    value, entry_id = updates[0]
    fields = normalize_account_update_fields(value, entry_id)
    assert fields["waba_id"] == "WABA123"
    assert fields["phone_number_id"] == "PN456"


def test_normalize_partner_app_installed_waba_info() -> None:
    value = {
        "event": "PARTNER_APP_INSTALLED",
        "waba_info": {
            "waba_id": "WABA_REAL",
            "owner_business_id": "PORTFOLIO99",
        },
    }
    fields = normalize_account_update_fields(value, "PORTFOLIO99")
    assert fields["waba_id"] == "WABA_REAL"
    assert fields["phone_number_id"] == ""
    assert fields["business_portfolio_id"] == "PORTFOLIO99"


def test_pick_default_phone_number_id_prefers_verified() -> None:
    rows = [
        {"id": "1", "code_verification_status": "NOT_VERIFIED"},
        {"id": "2", "code_verification_status": "VERIFIED"},
    ]
    assert pick_default_phone_number_id(rows) == "2"


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
        count = asyncio.run(process_account_update_webhook(payload))
    assert count == 0


def test_process_account_update_fetches_phone() -> None:
    payload = {
        "entry": [
            {
                "id": "PORT1",
                "changes": [
                    {
                        "field": "account_update",
                        "value": {
                            "event": "PARTNER_APP_INSTALLED",
                            "waba_info": {
                                "waba_id": "WABA99",
                                "owner_business_id": "PORT1",
                            },
                        },
                    }
                ],
            }
        ],
    }
    stored: list = []

    def _capture_add(obj: object) -> None:
        stored.append(obj)

    mock_session = MagicMock()
    mock_session.scalars.return_value.first.return_value = None
    mock_session.add.side_effect = _capture_add

    resolve_mock = AsyncMock(return_value="PN_RESOLVED")

    with (
        patch(
            "app.onboarding.account_update.resolve_phone_number_id_for_waba",
            resolve_mock,
        ),
        patch.dict(
            os.environ,
            {"META_SYSTEM_USER_ACCESS_TOKEN": "sys-token"},
            clear=False,
        ),
        patch("app.onboarding.account_update.session_scope") as mock_scope,
    ):
        mock_scope.return_value.__enter__.return_value = mock_session
        count = asyncio.run(process_account_update_webhook(payload))

    assert count == 1
    resolve_mock.assert_awaited_once_with("WABA99", "sys-token")
    assert len(stored) == 1
    assert stored[0].phone_number_id == "PN_RESOLVED"
    assert stored[0].waba_id == "WABA99"


def test_complete_onboarding_request_schema() -> None:
    body = CompleteOnboardingRequest(
        code="abc",
        waba_id="1",
        phone_number_id="2",
        pin="123456",
    )
    assert body.pin == "123456"

    body_no_phone = CompleteOnboardingRequest(code="abc", waba_id="1")
    assert body_no_phone.phone_number_id is None


def test_complete_onboarding_resolves_phone_from_waba() -> None:
    with (
        patch(
            "app.onboarding.service.exchange_code_for_business_token",
            new_callable=AsyncMock,
            return_value="biz-token",
        ),
        patch(
            "app.onboarding.service.resolve_phone_number_id_for_waba",
            new_callable=AsyncMock,
            return_value="PN_FROM_GRAPH",
        ),
        patch(
            "app.onboarding.service.subscribe_waba_webhooks",
            new_callable=AsyncMock,
        ),
        patch(
            "app.onboarding.service.register_phone_number",
            new_callable=AsyncMock,
        ),
        patch(
            "app.onboarding.service.get_phone_number_display",
            new_callable=AsyncMock,
            return_value="+54911",
        ),
        patch("app.onboarding.service.session_scope") as mock_scope,
        patch(
            "app.onboarding.service.get_tenant_by_phone_number_id",
            return_value=None,
        ),
    ):
        mock_session = MagicMock()
        mock_scope.return_value.__enter__.return_value = mock_session
        mock_session.scalars.return_value.all.return_value = []

        def _assign_tenant_id(obj: object) -> None:
            obj.id = 42  # type: ignore[attr-defined]

        mock_session.add.side_effect = _assign_tenant_id

        from app.onboarding.service import complete_onboarding

        result = asyncio.run(
            complete_onboarding(
                CompleteOnboardingRequest(code="c", waba_id="W1"),
            )
        )

    assert result.phone_number_id == "PN_FROM_GRAPH"
    assert result.tenant_id == 42


def test_get_pending_onboarding_session_prefers_platform_tenant() -> None:
    from app.onboarding.service import get_pending_onboarding_session

    row_a = MagicMock()
    row_a.id = 1
    row_a.status = "assets_received"
    row_a.tenant_id = None
    row_a.platform_tenant_id = 2
    row_a.waba_id = "WABA_A"
    row_a.phone_number_id = "P1"
    row_a.business_portfolio_id = None
    row_a.updated_at = 1

    row_b = MagicMock()
    row_b.id = 2
    row_b.status = "assets_received"
    row_b.tenant_id = None
    row_b.platform_tenant_id = 1
    row_b.waba_id = "WABA_B"
    row_b.phone_number_id = "P2"
    row_b.business_portfolio_id = None
    row_b.updated_at = 2

    mock_session = MagicMock()
    mock_session.scalars.return_value.all.return_value = [row_b, row_a]

    with patch.dict(os.environ, {"META_APP_ID": "APPID"}, clear=False):
        picked = get_pending_onboarding_session(mock_session, platform_tenant_id=1)

    assert picked is row_b


def test_get_pending_ignores_invalid_waba_app_id() -> None:
    from app.onboarding.service import get_pending_onboarding_session

    bad = MagicMock()
    bad.id = 1
    bad.status = "assets_received"
    bad.tenant_id = None
    bad.platform_tenant_id = None
    bad.waba_id = "APPID"
    bad.phone_number_id = None
    bad.business_portfolio_id = None

    good = MagicMock()
    good.id = 2
    good.status = "assets_received"
    good.tenant_id = None
    good.platform_tenant_id = None
    good.waba_id = "WABA_OK"
    good.phone_number_id = "P9"
    good.business_portfolio_id = None

    mock_session = MagicMock()
    mock_session.scalars.return_value.all.return_value = [bad, good]

    with patch.dict(os.environ, {"META_APP_ID": "APPID"}, clear=False):
        picked = get_pending_onboarding_session(mock_session)

    assert picked is good


def test_complete_without_waba_uses_pending_session() -> None:
    pending = MagicMock()
    pending.waba_id = "WABA_PENDING"
    pending.phone_number_id = "PN_PENDING"
    pending.business_portfolio_id = "BP1"
    pending.platform_tenant_id = 7

    with (
        patch(
            "app.onboarding.service.get_pending_onboarding_session",
            return_value=pending,
        ),
        patch(
            "app.onboarding.service.exchange_code_for_business_token",
            new_callable=AsyncMock,
            return_value="biz-token",
        ),
        patch(
            "app.onboarding.service.subscribe_waba_webhooks",
            new_callable=AsyncMock,
        ),
        patch(
            "app.onboarding.service.register_phone_number",
            new_callable=AsyncMock,
        ),
        patch(
            "app.onboarding.service.get_phone_number_display",
            new_callable=AsyncMock,
            return_value="+54911",
        ),
        patch("app.onboarding.service.session_scope") as mock_scope,
        patch(
            "app.onboarding.service.get_tenant_by_phone_number_id",
            return_value=None,
        ),
    ):
        mock_session = MagicMock()
        mock_scope.return_value.__enter__.return_value = mock_session
        mock_session.scalars.return_value.all.return_value = []

        def _assign_tenant_id(obj: object) -> None:
            obj.id = 99  # type: ignore[attr-defined]

        mock_session.add.side_effect = _assign_tenant_id

        from app.onboarding.service import complete_onboarding

        result = asyncio.run(
            complete_onboarding(
                CompleteOnboardingRequest(
                    code="c",
                    platform_tenant_id=7,
                ),
            )
        )

    assert result.waba_id == "WABA_PENDING"
    assert result.phone_number_id == "PN_PENDING"
    assert result.platform_tenant_id == 7
    assert result.tenant_id == 99
