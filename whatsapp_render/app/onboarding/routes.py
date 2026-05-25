from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_engine
from app.meta_graph import MetaGraphError, graph_version, meta_app_id
from app.onboarding.auth import require_onboarding_bearer
from app.onboarding.schemas import (
    CompleteOnboardingRequest,
    CompleteOnboardingResponse,
    OnboardingConfigResponse,
    OnboardingSessionResponse,
    SessionEventRequest,
    TenantConfigPatch,
    TenantStatusResponse,
)
from app.onboarding.service import (
    complete_onboarding,
    create_invite_session,
    get_onboarding_session_by_waba,
    get_pending_onboarding_session_response,
    get_tenant_status,
    patch_tenant_config,
    record_session_event,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.get("/config", response_model=OnboardingConfigResponse)
def onboarding_config() -> OnboardingConfigResponse:
    app_id = meta_app_id()
    config_id = os.environ.get("META_EMBEDDED_SIGNUP_CONFIG_ID", "").strip()
    return OnboardingConfigResponse(
        app_id=app_id,
        config_id=config_id,
        graph_version=graph_version(),
        configured=bool(app_id and config_id),
    )


@router.get(
    "/session/pending",
    response_model=OnboardingSessionResponse,
    dependencies=[Depends(require_onboarding_bearer)],
)
def onboarding_get_pending_session(
    platform_tenant_id: int | None = Query(None),
    waba_id: str | None = Query(None),
    phone_number_id: str | None = Query(None),
) -> OnboardingSessionResponse:
    if get_engine() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada")
    row = get_pending_onboarding_session_response(
        platform_tenant_id=platform_tenant_id,
        waba_id=waba_id,
        phone_number_id=phone_number_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Sesión pendiente no encontrada")
    return row


@router.get(
    "/session",
    response_model=OnboardingSessionResponse,
    dependencies=[Depends(require_onboarding_bearer)],
)
def onboarding_get_session(
    waba_id: str = Query(..., min_length=1),
) -> OnboardingSessionResponse:
    if get_engine() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada")
    row = get_onboarding_session_by_waba(waba_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return row


@router.post(
    "/session-event",
    dependencies=[Depends(require_onboarding_bearer)],
)
def onboarding_session_event(body: SessionEventRequest) -> dict[str, int | str]:
    if get_engine() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada")
    try:
        session_id = record_session_event(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "session_id": session_id}


@router.post(
    "/complete",
    response_model=CompleteOnboardingResponse,
    dependencies=[Depends(require_onboarding_bearer)],
)
async def onboarding_complete(body: CompleteOnboardingRequest) -> CompleteOnboardingResponse:
    if get_engine() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada")
    try:
        return await complete_onboarding(body)
    except MetaGraphError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/status/{tenant_id}",
    response_model=TenantStatusResponse,
    dependencies=[Depends(require_onboarding_bearer)],
)
def onboarding_status(tenant_id: int) -> TenantStatusResponse:
    if get_engine() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada")
    row = get_tenant_status(tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    return row


@router.patch(
    "/tenants/{tenant_id}",
    response_model=TenantStatusResponse,
    dependencies=[Depends(require_onboarding_bearer)],
)
def onboarding_patch_tenant(
    tenant_id: int,
    body: TenantConfigPatch,
) -> TenantStatusResponse:
    if get_engine() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada")
    updates = body.model_dump(exclude_unset=True)
    row = patch_tenant_config(tenant_id, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    return row


@router.post(
    "/invite",
    dependencies=[Depends(require_onboarding_bearer)],
)
def onboarding_create_invite() -> dict[str, str]:
    if get_engine() is None:
        raise HTTPException(status_code=503, detail="DATABASE_URL no configurada")
    return create_invite_session()
