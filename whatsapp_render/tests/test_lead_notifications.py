from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from app.leads import (
    format_lead_notification_subject,
    try_register_flow_alert,
)
from app.tenant_service import LeadNotificationSettings, _resolve_whatsapp_notify_to


def _fake_tenant(**kwargs: object) -> MagicMock:
    row = MagicMock()
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_resolve_whatsapp_notify_to_prefers_tenant() -> None:
    row = _fake_tenant(lead_alert_whatsapp_to="5491111111111")
    with patch.dict(os.environ, {"LEAD_WHATSAPP_NOTIFY_TO": "5492222222222"}, clear=False):
        assert _resolve_whatsapp_notify_to(row) == "5491111111111"


def test_resolve_whatsapp_notify_to_env_fallback() -> None:
    row = _fake_tenant(lead_alert_whatsapp_to="")
    with patch.dict(os.environ, {"LEAD_WHATSAPP_NOTIFY_TO": "5492222222222"}, clear=False):
        assert _resolve_whatsapp_notify_to(row) == "5492222222222"


def test_format_lead_notification_subject() -> None:
    assert format_lead_notification_subject("venta") == "Lead Compra - nuevo interés"
    assert format_lead_notification_subject("captacion") == "Lead Captación - nuevo interés"


def test_try_register_sends_whatsapp_only() -> None:
    settings = LeadNotificationSettings(
        email=None,
        whatsapp_to="5491111111111",
        email_enabled=False,
        whatsapp_enabled=True,
    )

    async def _run() -> None:
        with (
            patch("app.leads._lead_detection_enabled", return_value=True),
            patch("app.leads.get_engine", return_value=object()),
            patch("app.leads._upsert_lead", return_value=True),
            patch(
                "app.leads.fetch_lead_notification_settings",
                return_value=settings,
            ),
            patch(
                "app.leads._notify_agent_whatsapp",
                new_callable=AsyncMock,
            ) as mock_wa,
            patch(
                "app.leads._notify_agent_email",
                new_callable=AsyncMock,
            ) as mock_mail,
        ):
            await try_register_flow_alert(
                lead_type="venta",
                phone_number_id="pnid1",
                wa_id="54999",
                contact_name="Ana",
                property_ref="Depto Centro",
                interest_summary="Quiere visitar",
                conversation_summary="Busca alquiler",
                capture_summary=None,
                access_token="tok",
            )
            mock_wa.assert_awaited_once()
            mock_mail.assert_not_awaited()

    asyncio.run(_run())


def test_try_register_sends_email_only() -> None:
    settings = LeadNotificationSettings(
        email="dueño@test.com",
        whatsapp_to=None,
        email_enabled=True,
        whatsapp_enabled=False,
    )

    async def _run() -> None:
        with (
            patch("app.leads._lead_detection_enabled", return_value=True),
            patch("app.leads.get_engine", return_value=object()),
            patch("app.leads._upsert_lead", return_value=True),
            patch(
                "app.leads.fetch_lead_notification_settings",
                return_value=settings,
            ),
            patch(
                "app.leads._notify_agent_whatsapp",
                new_callable=AsyncMock,
            ) as mock_wa,
            patch(
                "app.leads._notify_agent_email",
                new_callable=AsyncMock,
            ) as mock_mail,
        ):
            await try_register_flow_alert(
                lead_type="alquiler",
                phone_number_id="pnid1",
                wa_id="54999",
                contact_name="Ana",
                property_ref="",
                interest_summary="Interés",
                conversation_summary="Resumen",
                capture_summary=None,
                access_token="tok",
            )
            mock_wa.assert_not_awaited()
            mock_mail.assert_awaited_once()

    asyncio.run(_run())


def test_try_register_sends_both_channels() -> None:
    settings = LeadNotificationSettings(
        email="dueño@test.com",
        whatsapp_to="5491111111111",
        email_enabled=True,
        whatsapp_enabled=True,
    )

    async def _run() -> None:
        with (
            patch("app.leads._lead_detection_enabled", return_value=True),
            patch("app.leads.get_engine", return_value=object()),
            patch("app.leads._upsert_lead", return_value=True),
            patch(
                "app.leads.fetch_lead_notification_settings",
                return_value=settings,
            ),
            patch(
                "app.leads._notify_agent_whatsapp",
                new_callable=AsyncMock,
            ) as mock_wa,
            patch(
                "app.leads._notify_agent_email",
                new_callable=AsyncMock,
            ) as mock_mail,
        ):
            await try_register_flow_alert(
                lead_type="captacion",
                phone_number_id="pnid1",
                wa_id="54999",
                contact_name="Juan",
                property_ref="",
                interest_summary="Vender casa",
                conversation_summary="Captación",
                capture_summary="tipo: Casa",
                access_token="tok",
            )
            mock_wa.assert_awaited_once()
            mock_mail.assert_awaited_once()

    asyncio.run(_run())


def test_try_register_skips_when_not_new_lead() -> None:
    async def _run() -> None:
        with (
            patch("app.leads._lead_detection_enabled", return_value=True),
            patch("app.leads.get_engine", return_value=object()),
            patch("app.leads._upsert_lead", return_value=False),
            patch(
                "app.leads.fetch_lead_notification_settings",
            ) as mock_fetch,
        ):
            await try_register_flow_alert(
                lead_type="venta",
                phone_number_id="pnid1",
                wa_id="54999",
                contact_name="Ana",
                property_ref="",
                interest_summary="Interés",
                conversation_summary="Resumen",
                capture_summary=None,
                access_token="tok",
            )
            mock_fetch.assert_not_called()

    asyncio.run(_run())


def test_try_register_sends_neither_when_disabled() -> None:
    settings = LeadNotificationSettings(
        email="dueño@test.com",
        whatsapp_to="5491111111111",
        email_enabled=False,
        whatsapp_enabled=False,
    )

    async def _run() -> None:
        with (
            patch("app.leads._lead_detection_enabled", return_value=True),
            patch("app.leads.get_engine", return_value=object()),
            patch("app.leads._upsert_lead", return_value=True),
            patch(
                "app.leads.fetch_lead_notification_settings",
                return_value=settings,
            ),
            patch(
                "app.leads._notify_agent_whatsapp",
                new_callable=AsyncMock,
            ) as mock_wa,
            patch(
                "app.leads._notify_agent_email",
                new_callable=AsyncMock,
            ) as mock_mail,
        ):
            await try_register_flow_alert(
                lead_type="venta",
                phone_number_id="pnid1",
                wa_id="54999",
                contact_name="Ana",
                property_ref="",
                interest_summary="Interés",
                conversation_summary="Resumen",
                capture_summary=None,
                access_token="tok",
            )
            mock_wa.assert_not_awaited()
            mock_mail.assert_not_awaited()

    asyncio.run(_run())


def test_notify_agent_email_skips_when_smtp_not_configured() -> None:
    from app.leads import _notify_agent_email

    async def _run() -> None:
        with (
            patch("app.leads.smtp_configured", return_value=False),
            patch("app.leads.send_email", new_callable=AsyncMock) as mock_send,
        ):
            await _notify_agent_email(
                lead_type="venta",
                notify_to="dueño@test.com",
                contact_name="Ana",
                wa_id="54999",
                property_ref="",
                interest_summary="Interés",
                conversation_summary="Resumen",
            )
            mock_send.assert_not_awaited()

    asyncio.run(_run())
