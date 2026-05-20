from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import session_scope
from app.models import OnboardingSession, Tenant

logger = logging.getLogger(__name__)


def _extract_account_updates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrae eventos account_update del payload del webhook Meta."""
    updates: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        waba_from_entry = str(entry.get("id") or "").strip()
        for change in entry.get("changes") or []:
            if str(change.get("field") or "") != "account_update":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            item = dict(value)
            if waba_from_entry and not item.get("waba_id"):
                item["waba_id"] = waba_from_entry
            updates.append(item)
    return updates


def process_account_update_webhook(payload: dict[str, Any]) -> int:
    """
    Respaldo si el panel no llamó a /complete: actualiza sesiones/tenants con IDs conocidos.
    No intercambia tokens (eso requiere el code del popup).
    """
    updates = _extract_account_updates(payload)
    if not updates:
        return 0

    handled = 0
    now = datetime.now(timezone.utc)

    for value in updates:
        event = str(value.get("event") or value.get("event_type") or "").strip()
        waba_id = str(
            value.get("waba_id")
            or value.get("whatsapp_business_account_id")
            or ""
        ).strip()
        phone_number_id = str(
            value.get("phone_number_id")
            or value.get("business_phone_number_id")
            or ""
        ).strip()
        business_id = str(
            value.get("business_id") or value.get("business_portfolio_id") or ""
        ).strip() or None

        logger.info(
            "account_update event=%s waba_id=%s phone_number_id=%s",
            event,
            waba_id,
            phone_number_id,
        )

        if not waba_id and not phone_number_id:
            continue

        try:
            with session_scope() as session:
                tenant: Tenant | None = None
                if phone_number_id:
                    tenant = session.scalars(
                        select(Tenant).where(Tenant.phone_number_id == phone_number_id)
                    ).first()
                if tenant is None and waba_id:
                    tenant = session.scalars(
                        select(Tenant).where(Tenant.waba_id == waba_id)
                    ).first()

                if tenant is not None:
                    if waba_id:
                        tenant.waba_id = waba_id
                    if business_id:
                        tenant.business_portfolio_id = business_id
                    if event.upper().endswith("INSTALLED") or event.upper().endswith("CONNECTED"):
                        if tenant.onboarding_status not in ("connected",):
                            tenant.onboarding_status = "pending_token"
                    handled += 1

                q = select(OnboardingSession).order_by(OnboardingSession.id.desc())
                if phone_number_id:
                    sess = session.scalars(
                        q.where(OnboardingSession.phone_number_id == phone_number_id)
                    ).first()
                elif waba_id:
                    sess = session.scalars(
                        q.where(OnboardingSession.waba_id == waba_id)
                    ).first()
                else:
                    sess = None

                if sess is None and (waba_id or phone_number_id):
                    sess = OnboardingSession(status="assets_received")
                    session.add(sess)

                if sess is not None:
                    if waba_id:
                        sess.waba_id = waba_id
                    if phone_number_id:
                        sess.phone_number_id = phone_number_id
                    if business_id:
                        sess.business_portfolio_id = business_id
                    sess.status = "assets_received"
                    sess.updated_at = now
                    handled += 1
        except Exception:
            logger.exception("account_update: error procesando evento")

    return handled
