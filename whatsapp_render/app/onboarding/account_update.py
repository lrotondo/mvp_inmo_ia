from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import session_scope
from app.meta_graph import (
    MetaGraphError,
    resolve_phone_number_id_for_waba,
    system_user_access_token,
)
from app.onboarding.ids import normalize_waba_id
from app.models import OnboardingSession, Tenant

logger = logging.getLogger(__name__)

WABA_SIN_NUMEROS = "waba_sin_numeros"


def _extract_account_updates(payload: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """Extrae eventos account_update: (value, entry_id)."""
    updates: list[tuple[dict[str, Any], str]] = []
    for entry in payload.get("entry") or []:
        entry_id = str(entry.get("id") or "").strip()
        for change in entry.get("changes") or []:
            if str(change.get("field") or "") != "account_update":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            updates.append((dict(value), entry_id))
    return updates


def normalize_account_update_fields(
    value: dict[str, Any],
    entry_id: str = "",
) -> dict[str, str | None]:
    """Normaliza PARTNER_APP_INSTALLED (waba_info) y payloads planos legacy."""
    waba_info = value.get("waba_info")
    has_waba_info = isinstance(waba_info, dict)

    if has_waba_info:
        waba_id = str(waba_info.get("waba_id") or "").strip()
        business_id = str(waba_info.get("owner_business_id") or "").strip() or None
    else:
        waba_id = str(
            value.get("waba_id")
            or value.get("whatsapp_business_account_id")
            or ""
        ).strip()
        business_id = (
            str(
                value.get("owner_business_id")
                or value.get("business_id")
                or value.get("business_portfolio_id")
                or ""
            ).strip()
            or None
        )

    if not waba_id and entry_id and not has_waba_info:
        waba_id = entry_id

    if not business_id and entry_id and has_waba_info:
        business_id = entry_id or None

    phone_number_id = str(
        value.get("phone_number_id") or value.get("business_phone_number_id") or ""
    ).strip()

    event = str(value.get("event") or value.get("event_type") or "").strip()

    return {
        "event": event,
        "waba_id": waba_id,
        "phone_number_id": phone_number_id,
        "business_portfolio_id": business_id,
    }


async def _fetch_phone_for_waba(waba_id: str) -> str | None:
    token = system_user_access_token()
    if not token:
        logger.warning(
            "account_update: sin META_SYSTEM_USER_ACCESS_TOKEN, no se puede "
            "resolver phone_number_id para waba_id=%s",
            waba_id,
        )
        return None
    try:
        return await resolve_phone_number_id_for_waba(waba_id, token)
    except MetaGraphError as exc:
        logger.warning(
            "account_update: fetch phone_numbers falló waba_id=%s: %s",
            waba_id,
            exc,
        )
        return None


async def process_account_update_webhook(payload: dict[str, Any]) -> int:
    """
    Respaldo si el panel no llamó a /complete: actualiza sesiones/tenants con IDs conocidos.
    Si falta phone_number_id (p. ej. PARTNER_APP_INSTALLED), consulta Graph API.
    No intercambia tokens (eso requiere el code del popup).
    """
    raw_updates = _extract_account_updates(payload)
    if not raw_updates:
        return 0

    handled = 0
    now = datetime.now(timezone.utc)

    for value, entry_id in raw_updates:
        fields = normalize_account_update_fields(value, entry_id)
        event = fields["event"] or ""
        waba_id = normalize_waba_id(fields["waba_id"] or "")
        phone_number_id = fields["phone_number_id"] or ""
        business_id = fields["business_portfolio_id"]

        if waba_id and not phone_number_id:
            resolved = await _fetch_phone_for_waba(waba_id)
            if resolved:
                phone_number_id = resolved
                logger.info(
                    "account_update: phone_number_id resuelto vía Graph waba_id=%s phone=%s",
                    waba_id,
                    phone_number_id,
                )

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
                    if event.upper().endswith("INSTALLED") or event.upper().endswith(
                        "CONNECTED"
                    ):
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
                        sess.error_message = None
                    elif waba_id and not phone_number_id:
                        sess.error_message = WABA_SIN_NUMEROS
                    if business_id:
                        sess.business_portfolio_id = business_id
                    sess.status = "assets_received"
                    sess.updated_at = now
                    handled += 1
        except Exception:
            logger.exception("account_update: error procesando evento")

    return handled
