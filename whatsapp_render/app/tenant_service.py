from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import resolve_rent_catalog_path
from app.db import get_engine, session_scope
from app.models import Tenant


@dataclass(frozen=True)
class TenantContext:
    phone_number_id: str
    access_token: str
    name: str | None
    system_prompt: str | None
    catalog_csv_path: str | None
    catalog_rent_csv_path: str | None
    office_hours: str | None = None
    office_address: str | None = None
    social_links: str | None = None


@dataclass(frozen=True)
class InstitutionalProfile:
    office_hours: str | None
    office_address: str | None
    social_links: str | None


@dataclass(frozen=True)
class LeadNotificationSettings:
    email: str | None
    whatsapp_to: str | None
    email_enabled: bool
    whatsapp_enabled: bool


def get_tenant_by_phone_number_id(session: Session, phone_number_id: str) -> Tenant | None:
    if not phone_number_id:
        return None
    stmt = select(Tenant).where(Tenant.phone_number_id == phone_number_id.strip())
    return session.scalars(stmt).first()


def fetch_tenant_context(phone_number_id: str) -> TenantContext | None:
    if not phone_number_id or not phone_number_id.strip():
        return None
    if get_engine() is None:
        return None
    with session_scope() as session:
        row = get_tenant_by_phone_number_id(session, phone_number_id)
        if row is None:
            return None
        rent_path = resolve_rent_catalog_path(
            row.catalog_csv_path,
            row.catalog_rent_csv_path,
        )
        return TenantContext(
            phone_number_id=row.phone_number_id,
            access_token=row.access_token,
            name=row.name,
            system_prompt=row.system_prompt,
            catalog_csv_path=row.catalog_csv_path,
            catalog_rent_csv_path=rent_path,
            office_hours=(row.office_hours or "").strip() or None,
            office_address=(row.office_address or "").strip() or None,
            social_links=(row.social_links or "").strip() or None,
        )


def fetch_institutional_profile(phone_number_id: str) -> InstitutionalProfile | None:
    if not phone_number_id or not phone_number_id.strip():
        return None
    if get_engine() is None:
        return None
    with session_scope() as session:
        row = get_tenant_by_phone_number_id(session, phone_number_id)
        if row is None:
            return None
        return InstitutionalProfile(
            office_hours=(row.office_hours or "").strip() or None,
            office_address=(row.office_address or "").strip() or None,
            social_links=(row.social_links or "").strip() or None,
        )


def _resolve_whatsapp_notify_to(row: Tenant) -> str | None:
    tenant_num = (row.lead_alert_whatsapp_to or "").strip()
    if tenant_num:
        return tenant_num
    env_num = (os.environ.get("LEAD_WHATSAPP_NOTIFY_TO") or "").strip()
    return env_num or None


def fetch_lead_notification_settings(
    phone_number_id: str,
) -> LeadNotificationSettings | None:
    if not phone_number_id or not phone_number_id.strip():
        return None
    if get_engine() is None:
        return None
    with session_scope() as session:
        row = get_tenant_by_phone_number_id(session, phone_number_id)
        if row is None:
            return None
        email = (row.lead_alert_email or "").strip() or None
        whatsapp_to = _resolve_whatsapp_notify_to(row)
        email_enabled = bool(row.lead_notify_email_enabled)
        whatsapp_enabled = bool(row.lead_notify_whatsapp_enabled)
        return LeadNotificationSettings(
            email=email,
            whatsapp_to=whatsapp_to,
            email_enabled=email_enabled,
            whatsapp_enabled=whatsapp_enabled,
        )
