from __future__ import annotations

import argparse
import sys

from app.db import init_db, session_scope
from app.models import Tenant
from app.tenant_service import get_tenant_by_phone_number_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Alta o actualizacion manual de un tenant (inmobiliaria).")
    parser.add_argument("--phone-number-id", required=True, help="Phone Number ID de Meta (WABA).")
    parser.add_argument("--access-token", required=True, help="Token de acceso de WhatsApp Cloud API.")
    parser.add_argument("--name", default="", help="Nombre visible (opcional).")
    parser.add_argument(
        "--system-prompt",
        default="",
        help="Prompt de sistema personalizado (opcional). Vacio = default del codigo.",
    )
    parser.add_argument(
        "--catalog-csv-path",
        default="",
        help="Venta: ruta CSV (data/tenants/foo.csv) o URL/ID de Google Sheet.",
    )
    parser.add_argument(
        "--catalog-rent-csv-path",
        default="",
        help="Alquiler: ruta CSV o URL/ID de Google Sheet (obligatorio si venta es Sheet).",
    )
    parser.add_argument(
        "--catalog-sheet-url",
        default="",
        help="Alias de --catalog-csv-path para URL/ID del Sheet de venta.",
    )
    parser.add_argument(
        "--catalog-rent-sheet-url",
        default="",
        help="Alias de --catalog-rent-csv-path para URL/ID del Sheet de alquiler.",
    )
    args = parser.parse_args()

    if init_db() is None:
        print("Error: define DATABASE_URL (Postgres) antes de ejecutar este script.", file=sys.stderr)
        sys.exit(1)

    name = args.name.strip() or None
    system_prompt = args.system_prompt.strip() or None
    catalog = (
        args.catalog_sheet_url.strip()
        or args.catalog_csv_path.strip()
        or None
    )
    catalog_rent = (
        args.catalog_rent_sheet_url.strip()
        or args.catalog_rent_csv_path.strip()
        or None
    )

    with session_scope() as session:
        row = get_tenant_by_phone_number_id(session, args.phone_number_id)
        if row is None:
            session.add(
                Tenant(
                    phone_number_id=args.phone_number_id.strip(),
                    access_token=args.access_token.strip(),
                    name=name,
                    system_prompt=system_prompt,
                    catalog_csv_path=catalog,
                    catalog_rent_csv_path=catalog_rent,
                    onboarding_status="manual",
                )
            )
            action = "creado"
        else:
            row.access_token = args.access_token.strip()
            row.name = name
            row.system_prompt = system_prompt
            row.catalog_csv_path = catalog
            row.catalog_rent_csv_path = catalog_rent
            if not row.onboarding_status:
                row.onboarding_status = "manual"
            action = "actualizado"

    print(f"Tenant {action}: phone_number_id={args.phone_number_id.strip()!r}")


if __name__ == "__main__":
    main()
