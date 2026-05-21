#!/usr/bin/env python3
"""
Migra filas de tenants desde Postgres (OLD_DATABASE_URL) o CSV hacia MySQL (DATABASE_URL).

Uso:
  set OLD_DATABASE_URL=postgresql://...
  set DATABASE_URL=mysql+pymysql://...
  python scripts/migrate_tenants_to_mysql.py

  python scripts/migrate_tenants_to_mysql.py --csv tenants_export.csv

Solo migra tenants; chats/leads/waitlist quedan vacíos en MySQL.
Para leer Postgres hace falta psycopg una vez: pip install "psycopg[binary]"
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Raíz del paquete whatsapp_render
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select, text
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.db import dispose_engine, get_engine, init_db, session_scope
from app.models import Tenant

TENANT_COLUMNS = [
    "phone_number_id",
    "access_token",
    "name",
    "system_prompt",
    "catalog_csv_path",
    "catalog_rent_csv_path",
    "waba_id",
    "business_portfolio_id",
    "onboarding_status",
    "onboarding_error",
    "connected_at",
    "token_expires_at",
]


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    status = (data.get("onboarding_status") or "").strip() or "manual"
    return {
        "phone_number_id": str(data.get("phone_number_id") or "").strip(),
        "access_token": str(data.get("access_token") or "").strip(),
        "name": (data.get("name") or None) or None,
        "system_prompt": (data.get("system_prompt") or None) or None,
        "catalog_csv_path": (data.get("catalog_csv_path") or None) or None,
        "catalog_rent_csv_path": (data.get("catalog_rent_csv_path") or None) or None,
        "waba_id": (data.get("waba_id") or None) or None,
        "business_portfolio_id": (data.get("business_portfolio_id") or None) or None,
        "onboarding_status": status,
        "onboarding_error": (data.get("onboarding_error") or None) or None,
        "connected_at": _parse_dt(data.get("connected_at")),
        "token_expires_at": _parse_dt(data.get("token_expires_at")),
    }


def load_rows_from_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = _row_from_dict(raw)
            if row["phone_number_id"] and row["access_token"]:
                rows.append(row)
    return rows


def load_rows_from_postgres(old_url: str) -> list[dict[str, Any]]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session, sessionmaker

    from app.db import _normalize_database_url

    url = _normalize_database_url(old_url)
    if not url.startswith("postgresql"):
        print("OLD_DATABASE_URL debe ser PostgreSQL.", file=sys.stderr)
        sys.exit(1)

    try:
        engine = create_engine(url, pool_pre_ping=True)
    except Exception as exc:
        print(
            "No se pudo conectar a Postgres. Para migración one-shot: "
            'pip install "psycopg[binary]"',
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    factory = sessionmaker(bind=engine)
    rows: list[dict[str, Any]] = []
    with factory() as session:
        result = session.execute(
            text(
                """
                SELECT phone_number_id, access_token, name, system_prompt,
                       catalog_csv_path, catalog_rent_csv_path,
                       waba_id, business_portfolio_id, onboarding_status,
                       onboarding_error, connected_at, token_expires_at
                FROM tenants
                ORDER BY id
                """
            )
        )
        keys = list(result.keys())
        for record in result.fetchall():
            data = dict(zip(keys, record))
            row = _row_from_dict(data)
            if row["phone_number_id"] and row["access_token"]:
                rows.append(row)
    engine.dispose()
    return rows


def upsert_tenants_mysql(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    count = 0
    with session_scope() as session:
        for row in rows:
            stmt = mysql_insert(Tenant).values(**row)
            stmt = stmt.on_duplicate_key_update(
                access_token=stmt.inserted.access_token,
                name=stmt.inserted.name,
                system_prompt=stmt.inserted.system_prompt,
                catalog_csv_path=stmt.inserted.catalog_csv_path,
                catalog_rent_csv_path=stmt.inserted.catalog_rent_csv_path,
                waba_id=stmt.inserted.waba_id,
                business_portfolio_id=stmt.inserted.business_portfolio_id,
                onboarding_status=stmt.inserted.onboarding_status,
                onboarding_error=stmt.inserted.onboarding_error,
                connected_at=stmt.inserted.connected_at,
                token_expires_at=stmt.inserted.token_expires_at,
            )
            session.execute(stmt)
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrar tenants a MySQL.")
    parser.add_argument(
        "--csv",
        type=Path,
        help="CSV exportado desde Postgres (cabeceras = columnas tenants)",
    )
    parser.add_argument(
        "--old-url",
        default=os.environ.get("OLD_DATABASE_URL", "").strip(),
        help="URL Postgres origen (o env OLD_DATABASE_URL)",
    )
    parser.add_argument(
        "--skip-init",
        action="store_true",
        help="No ejecutar create_all; asumir tablas ya creadas",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL", "").strip():
        print("Error: define DATABASE_URL (MySQL destino).", file=sys.stderr)
        sys.exit(1)

    dispose_engine()
    if args.skip_init:
        if get_engine() is None:
            print("Error: DATABASE_URL inválida.", file=sys.stderr)
            sys.exit(1)
    else:
        if init_db() is None:
            print("Error: no se pudo inicializar MySQL.", file=sys.stderr)
            sys.exit(1)

    if args.csv:
        if not args.csv.is_file():
            print(f"CSV no encontrado: {args.csv}", file=sys.stderr)
            sys.exit(1)
        rows = load_rows_from_csv(args.csv)
        source = f"CSV {args.csv}"
    elif args.old_url:
        rows = load_rows_from_postgres(args.old_url)
        source = "Postgres OLD_DATABASE_URL"
    else:
        print("Indicá --csv o OLD_DATABASE_URL / --old-url.", file=sys.stderr)
        sys.exit(1)

    n = upsert_tenants_mysql(rows)
    print(f"Migrados/actualizados {n} tenants desde {source}.")

    with session_scope() as session:
        total = session.scalars(select(Tenant)).all()
        print(f"Total en MySQL tenants: {len(total)}")


if __name__ == "__main__":
    main()
