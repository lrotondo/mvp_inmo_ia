from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.meta_graph import (
    MetaGraphError,
    exchange_code_for_business_token,
    get_phone_number_display,
    register_phone_number,
    resolve_phone_number_id_for_waba,
    subscribe_waba_webhooks,
)
from app.models import OnboardingSession, Tenant
from app.onboarding.schemas import (
    CompleteOnboardingRequest,
    CompleteOnboardingResponse,
    OnboardingSessionResponse,
    SessionEventRequest,
    TenantStatusResponse,
)
from app.tenant_service import get_tenant_by_phone_number_id

logger = logging.getLogger(__name__)

ONBOARDING_STATUS_CONNECTED = "connected"
ONBOARDING_STATUS_FAILED = "failed"
ONBOARDING_STATUS_PENDING = "pending"
ONBOARDING_STATUS_MANUAL = "manual"


def _default_catalog_sale() -> str | None:
    raw = os.environ.get("ONBOARDING_DEFAULT_CATALOG_SALE_PATH", "").strip()
    return raw or None


def _default_catalog_rent() -> str | None:
    raw = os.environ.get("ONBOARDING_DEFAULT_CATALOG_RENT_PATH", "").strip()
    return raw or None


def _generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def record_session_event(body: SessionEventRequest) -> int:
    waba_id = body.waba_id.strip()
    phone = (body.phone_number_id or "").strip()
    with session_scope() as session:
        row: OnboardingSession | None = None
        if body.invite_token:
            row = session.scalars(
                select(OnboardingSession).where(
                    OnboardingSession.invite_token == body.invite_token.strip()
                )
            ).first()
        if row is None and phone:
            row = session.scalars(
                select(OnboardingSession)
                .where(OnboardingSession.phone_number_id == phone)
                .order_by(OnboardingSession.id.desc())
            ).first()
        if row is None and waba_id:
            row = session.scalars(
                select(OnboardingSession)
                .where(OnboardingSession.waba_id == waba_id)
                .order_by(OnboardingSession.id.desc())
            ).first()
        if row is None:
            row = OnboardingSession(
                invite_token=body.invite_token.strip() if body.invite_token else None,
                status="assets_received",
            )
            session.add(row)
        row.waba_id = waba_id
        if phone:
            row.phone_number_id = phone
            row.error_message = None
        if body.business_portfolio_id:
            row.business_portfolio_id = body.business_portfolio_id.strip()
        row.status = "assets_received"
        session.flush()
        return int(row.id)


def get_onboarding_session_by_waba(waba_id: str) -> OnboardingSessionResponse | None:
    wid = (waba_id or "").strip()
    if not wid:
        return None
    with session_scope() as session:
        row = session.scalars(
            select(OnboardingSession)
            .where(OnboardingSession.waba_id == wid)
            .order_by(OnboardingSession.id.desc())
        ).first()
        if row is None:
            return None
        return OnboardingSessionResponse(
            session_id=int(row.id),
            waba_id=row.waba_id,
            phone_number_id=row.phone_number_id,
            status=row.status,
            error_message=row.error_message,
        )


async def complete_onboarding(body: CompleteOnboardingRequest) -> CompleteOnboardingResponse:
    waba_id = body.waba_id.strip()
    phone_number_id = (body.phone_number_id or "").strip()
    business_portfolio_id = (body.business_portfolio_id or "").strip() or None
    name = (body.name or "").strip() or None
    pin = (body.pin or "").strip() or _generate_pin()

    try:
        business_token = await exchange_code_for_business_token(body.code)
        if not phone_number_id and waba_id:
            phone_number_id = (
                await resolve_phone_number_id_for_waba(waba_id, business_token) or ""
            )
        if not phone_number_id:
            raise MetaGraphError(
                "El WABA no tiene números registrados; agregá un teléfono en Meta "
                "Business Suite y volvé a conectar."
            )
        await subscribe_waba_webhooks(waba_id, business_token)
        if not body.skip_register:
            await register_phone_number(phone_number_id, business_token, pin)
        display_phone = await get_phone_number_display(phone_number_id, business_token)
    except MetaGraphError as exc:
        logger.warning(
            "onboarding complete failed waba=%s phone=%s: %s",
            waba_id,
            phone_number_id,
            exc,
        )
        _mark_failed(waba_id, phone_number_id, str(exc))
        raise

    catalog_sale = (body.catalog_csv_path or "").strip() or _default_catalog_sale()
    catalog_rent = (body.catalog_rent_csv_path or "").strip() or _default_catalog_rent()
    now = datetime.now(timezone.utc)

    with session_scope() as session:
        tenant = get_tenant_by_phone_number_id(session, phone_number_id)
        if tenant is None:
            tenant = Tenant(
                phone_number_id=phone_number_id,
                access_token=business_token,
                name=name,
                catalog_csv_path=catalog_sale,
                catalog_rent_csv_path=catalog_rent,
                waba_id=waba_id,
                business_portfolio_id=business_portfolio_id,
                onboarding_status=ONBOARDING_STATUS_CONNECTED,
                onboarding_error=None,
                connected_at=now,
            )
            session.add(tenant)
        else:
            tenant.access_token = business_token
            if name:
                tenant.name = name
            tenant.waba_id = waba_id
            tenant.business_portfolio_id = business_portfolio_id
            tenant.onboarding_status = ONBOARDING_STATUS_CONNECTED
            tenant.onboarding_error = None
            tenant.connected_at = now
            if catalog_sale:
                tenant.catalog_csv_path = catalog_sale
            if catalog_rent:
                tenant.catalog_rent_csv_path = catalog_rent
        session.flush()
        tenant_id = int(tenant.id)

        sessions_by_phone = session.scalars(
            select(OnboardingSession).where(
                OnboardingSession.phone_number_id == phone_number_id
            )
        ).all()
        sessions_by_waba = session.scalars(
            select(OnboardingSession).where(OnboardingSession.waba_id == waba_id)
        ).all()
        seen_ids: set[int] = set()
        for sess in list(sessions_by_phone) + list(sessions_by_waba):
            if sess.id in seen_ids:
                continue
            seen_ids.add(int(sess.id))
            sess.status = ONBOARDING_STATUS_CONNECTED
            sess.tenant_id = tenant_id
            sess.phone_number_id = phone_number_id
            sess.error_message = None

    logger.info(
        "onboarding connected tenant_id=%s phone_number_id=%s waba_id=%s",
        tenant_id,
        phone_number_id,
        waba_id,
    )
    return CompleteOnboardingResponse(
        ok=True,
        tenant_id=tenant_id,
        phone_number_id=phone_number_id,
        waba_id=waba_id,
        display_phone=display_phone,
        onboarding_status=ONBOARDING_STATUS_CONNECTED,
    )


def _mark_failed(waba_id: str, phone_number_id: str, error: str) -> None:
    try:
        with session_scope() as session:
            tenant = None
            if phone_number_id:
                tenant = get_tenant_by_phone_number_id(session, phone_number_id)
            if tenant is None and waba_id:
                tenant = session.scalars(
                    select(Tenant).where(Tenant.waba_id == waba_id)
                ).first()
            if tenant is not None:
                tenant.onboarding_status = ONBOARDING_STATUS_FAILED
                tenant.onboarding_error = error[:2000]
            sessions: list[OnboardingSession] = []
            if phone_number_id:
                sessions = list(
                    session.scalars(
                        select(OnboardingSession).where(
                            OnboardingSession.phone_number_id == phone_number_id
                        )
                    ).all()
                )
            elif waba_id:
                sessions = list(
                    session.scalars(
                        select(OnboardingSession).where(
                            OnboardingSession.waba_id == waba_id
                        )
                    ).all()
                )
            for sess in sessions:
                sess.status = ONBOARDING_STATUS_FAILED
                sess.error_message = error[:2000]
    except Exception:
        logger.exception("onboarding: no se pudo marcar failed")


def get_tenant_status(tenant_id: int) -> TenantStatusResponse | None:
    with session_scope() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            return None
        connected = tenant.connected_at.isoformat() if tenant.connected_at else None
        return TenantStatusResponse(
            tenant_id=int(tenant.id),
            phone_number_id=tenant.phone_number_id,
            waba_id=tenant.waba_id,
            name=tenant.name,
            onboarding_status=tenant.onboarding_status or ONBOARDING_STATUS_MANUAL,
            onboarding_error=tenant.onboarding_error,
            connected_at=connected,
            catalog_csv_path=tenant.catalog_csv_path,
            catalog_rent_csv_path=tenant.catalog_rent_csv_path,
        )


def patch_tenant_config(tenant_id: int, **fields: str | None) -> TenantStatusResponse | None:
    with session_scope() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            return None
        if fields.get("name") is not None:
            tenant.name = fields["name"].strip() or None
        if fields.get("system_prompt") is not None:
            tenant.system_prompt = fields["system_prompt"].strip() or None
        if fields.get("catalog_csv_path") is not None:
            tenant.catalog_csv_path = fields["catalog_csv_path"].strip() or None
        if fields.get("catalog_rent_csv_path") is not None:
            tenant.catalog_rent_csv_path = fields["catalog_rent_csv_path"].strip() or None
        session.flush()
    return get_tenant_status(tenant_id)


def create_invite_session() -> dict[str, str]:
    token = secrets.token_urlsafe(24)
    with session_scope() as session:
        session.add(
            OnboardingSession(
                invite_token=token,
                status=ONBOARDING_STATUS_PENDING,
            )
        )
    return {"invite_token": token, "status": ONBOARDING_STATUS_PENDING}
