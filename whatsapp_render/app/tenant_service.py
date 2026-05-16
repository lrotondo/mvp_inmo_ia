from __future__ import annotations

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
        )
