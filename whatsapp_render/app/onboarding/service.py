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
from app.onboarding.ids import is_invalid_waba_id, normalize_waba_id
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
ASSETS_RECEIVED_STATUS = "assets_received"


def _default_catalog_sale() -> str | None:
    raw = os.environ.get("ONBOARDING_DEFAULT_CATALOG_SALE_PATH", "").strip()
    return raw or None


def _default_catalog_rent() -> str | None:
    raw = os.environ.get("ONBOARDING_DEFAULT_CATALOG_RENT_PATH", "").strip()
    return raw or None


def _generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _session_to_response(row: OnboardingSession) -> OnboardingSessionResponse:
    return OnboardingSessionResponse(
        session_id=int(row.id),
        waba_id=row.waba_id,
        phone_number_id=row.phone_number_id,
        status=row.status,
        error_message=row.error_message,
        platform_tenant_id=row.platform_tenant_id,
        business_portfolio_id=row.business_portfolio_id,
    )


def get_pending_onboarding_session(
    session: Session,
    *,
    platform_tenant_id: int | None = None,
    waba_id: str | None = None,
    phone_number_id: str | None = None,
) -> OnboardingSession | None:
    """Sesión assets_received sin tenant, priorizando platform_tenant_id y phone resuelto."""
    rows = list(
        session.scalars(
            select(OnboardingSession)
            .where(
                OnboardingSession.status == ASSETS_RECEIVED_STATUS,
                OnboardingSession.tenant_id.is_(None),
            )
            .order_by(OnboardingSession.updated_at.desc())
        ).all()
    )

    def usable(row: OnboardingSession) -> bool:
        if row.phone_number_id:
            return True
        return not is_invalid_waba_id(row.waba_id)

    candidates = [r for r in rows if usable(r)]
    if not candidates:
        return None

    if platform_tenant_id is not None:
        scoped = [r for r in candidates if r.platform_tenant_id == platform_tenant_id]
        if scoped:
            candidates = scoped

    waba_clean = normalize_waba_id(waba_id)
    if waba_clean:
        match = next((r for r in candidates if r.waba_id == waba_clean), None)
        if match:
            return match

    phone_clean = (phone_number_id or "").strip()
    if phone_clean:
        match = next((r for r in candidates if r.phone_number_id == phone_clean), None)
        if match:
            return match

    with_phone = [r for r in candidates if r.phone_number_id]
    if with_phone:
        return with_phone[0]

    return candidates[0]


def record_session_event(body: SessionEventRequest) -> int:
    waba_id = normalize_waba_id(body.waba_id)
    phone = (body.phone_number_id or "").strip()
    platform_id = body.platform_tenant_id
    if not waba_id and not phone and platform_id is None:
        raise ValueError(
            "session-event requiere waba_id, phone_number_id o platform_tenant_id"
        )
    with session_scope() as session:
        row: OnboardingSession | None = None
        if body.invite_token:
            row = session.scalars(
                select(OnboardingSession).where(
                    OnboardingSession.invite_token == body.invite_token.strip()
                )
            ).first()
        if row is None and platform_id is not None:
            row = session.scalars(
                select(OnboardingSession)
                .where(
                    OnboardingSession.platform_tenant_id == platform_id,
                    OnboardingSession.status == ASSETS_RECEIVED_STATUS,
                    OnboardingSession.tenant_id.is_(None),
                )
                .order_by(OnboardingSession.id.desc())
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
                status=ASSETS_RECEIVED_STATUS,
            )
            session.add(row)
        if waba_id:
            row.waba_id = waba_id
        if phone:
            row.phone_number_id = phone
            row.error_message = None
        if body.business_portfolio_id:
            row.business_portfolio_id = body.business_portfolio_id.strip()
        if platform_id is not None:
            row.platform_tenant_id = platform_id
        row.status = ASSETS_RECEIVED_STATUS
        session.flush()
        return int(row.id)


def get_onboarding_session_by_waba(waba_id: str) -> OnboardingSessionResponse | None:
    wid = normalize_waba_id(waba_id)
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
        return _session_to_response(row)


def get_pending_onboarding_session_response(
    *,
    platform_tenant_id: int | None = None,
    waba_id: str | None = None,
    phone_number_id: str | None = None,
) -> OnboardingSessionResponse | None:
    with session_scope() as session:
        row = get_pending_onboarding_session(
            session,
            platform_tenant_id=platform_tenant_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
        )
        if row is None:
            return None
        return _session_to_response(row)


def _resolve_assets_from_pending(
    body: CompleteOnboardingRequest,
    pending: OnboardingSessionResponse | None,
) -> tuple[str, str, str | None, int | None]:
    waba_id = normalize_waba_id(body.waba_id)
    phone_number_id = (body.phone_number_id or "").strip()
    business_portfolio_id = (body.business_portfolio_id or "").strip() or None
    platform_id = body.platform_tenant_id

    if pending is not None:
        if not waba_id and pending.waba_id and not is_invalid_waba_id(pending.waba_id):
            waba_id = (pending.waba_id or "").strip()
        if not phone_number_id and pending.phone_number_id:
            phone_number_id = (pending.phone_number_id or "").strip()
        if not business_portfolio_id and pending.business_portfolio_id:
            business_portfolio_id = pending.business_portfolio_id
        if platform_id is None and pending.platform_tenant_id is not None:
            platform_id = pending.platform_tenant_id

    return waba_id, phone_number_id, business_portfolio_id, platform_id


async def complete_onboarding(body: CompleteOnboardingRequest) -> CompleteOnboardingResponse:
    with session_scope() as session:
        pending_row = get_pending_onboarding_session(
            session,
            platform_tenant_id=body.platform_tenant_id,
            waba_id=body.waba_id,
            phone_number_id=body.phone_number_id,
        )
        pending = _session_to_response(pending_row) if pending_row else None

    waba_id, phone_number_id, business_portfolio_id, platform_id = _resolve_assets_from_pending(
        body, pending
    )
    name = (body.name or "").strip() or None
    pin = (body.pin or "").strip() or _generate_pin()

    try:
        business_token = await exchange_code_for_business_token(body.code)
        if not waba_id and not phone_number_id:
            raise MetaGraphError(
                "No hay sesión de onboarding pendiente. Completá el popup de Meta "
                "o esperá unos segundos y volvé a intentar."
            )
        if not phone_number_id and waba_id:
            phone_number_id = (
                await resolve_phone_number_id_for_waba(waba_id, business_token) or ""
            )
        if not waba_id and phone_number_id:
            raise MetaGraphError(
                "Falta el WABA de la cuenta. Volvé a conectar desde el panel."
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
            "onboarding complete failed waba=%s phone=%s platform=%s: %s",
            waba_id,
            phone_number_id,
            platform_id,
            exc,
        )
        _mark_failed(waba_id, phone_number_id, str(exc), platform_tenant_id=platform_id)
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
                platform_tenant_id=platform_id,
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
            if platform_id is not None:
                tenant.platform_tenant_id = platform_id
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
        if platform_id is not None:
            sessions_by_platform = session.scalars(
                select(OnboardingSession).where(
                    OnboardingSession.platform_tenant_id == platform_id
                )
            ).all()
        else:
            sessions_by_platform = []

        seen_ids: set[int] = set()
        for sess in (
            list(sessions_by_phone)
            + list(sessions_by_waba)
            + list(sessions_by_platform)
        ):
            if sess.id in seen_ids:
                continue
            seen_ids.add(int(sess.id))
            sess.status = ONBOARDING_STATUS_CONNECTED
            sess.tenant_id = tenant_id
            sess.phone_number_id = phone_number_id
            sess.waba_id = waba_id
            if platform_id is not None:
                sess.platform_tenant_id = platform_id
            sess.error_message = None

    logger.info(
        "onboarding connected tenant_id=%s platform_tenant_id=%s phone_number_id=%s waba_id=%s",
        tenant_id,
        platform_id,
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
        platform_tenant_id=platform_id,
    )


def _mark_failed(
    waba_id: str,
    phone_number_id: str,
    error: str,
    *,
    platform_tenant_id: int | None = None,
) -> None:
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
            elif platform_tenant_id is not None:
                sessions = list(
                    session.scalars(
                        select(OnboardingSession).where(
                            OnboardingSession.platform_tenant_id == platform_tenant_id
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
            platform_tenant_id=tenant.platform_tenant_id,
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
