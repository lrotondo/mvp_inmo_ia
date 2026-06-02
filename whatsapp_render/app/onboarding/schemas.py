from __future__ import annotations

from pydantic import BaseModel, Field


class OnboardingConfigResponse(BaseModel):
    app_id: str
    config_id: str
    graph_version: str
    configured: bool


class SessionEventRequest(BaseModel):
    waba_id: str | None = None
    phone_number_id: str | None = None
    business_portfolio_id: str | None = None
    event: str | None = None
    invite_token: str | None = None
    platform_tenant_id: int | None = None


class OnboardingSessionResponse(BaseModel):
    session_id: int
    waba_id: str | None = None
    phone_number_id: str | None = None
    status: str
    error_message: str | None = None
    platform_tenant_id: int | None = None
    business_portfolio_id: str | None = None


class CompleteOnboardingRequest(BaseModel):
    code: str = Field(..., min_length=1)
    waba_id: str | None = None
    phone_number_id: str | None = None
    business_portfolio_id: str | None = None
    event: str | None = None
    name: str | None = None
    pin: str | None = Field(None, min_length=6, max_length=6)
    skip_register: bool = False
    catalog_csv_path: str | None = None
    catalog_rent_csv_path: str | None = None
    platform_tenant_id: int | None = None


class CompleteOnboardingResponse(BaseModel):
    ok: bool
    tenant_id: int
    phone_number_id: str
    waba_id: str
    display_phone: str | None = None
    onboarding_status: str
    platform_tenant_id: int | None = None


class TenantStatusResponse(BaseModel):
    tenant_id: int
    phone_number_id: str
    waba_id: str | None
    name: str | None
    onboarding_status: str
    onboarding_error: str | None
    connected_at: str | None
    catalog_csv_path: str | None
    catalog_rent_csv_path: str | None
    platform_tenant_id: int | None = None
    office_hours: str | None = None
    office_address: str | None = None
    social_links: str | None = None


class TenantConfigPatch(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    catalog_csv_path: str | None = None
    catalog_rent_csv_path: str | None = None
    office_hours: str | None = None
    office_address: str | None = None
    social_links: str | None = None
