#!/usr/bin/env python3
"""Agrega columnas institucionales a tenants (idempotente)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import inspect, text

from app.db import dispose_engine, get_engine, init_db

_COLUMNS = (
    ("office_hours", "TEXT NULL"),
    ("office_address", "TEXT NULL"),
    ("social_links", "TEXT NULL"),
)


def main() -> int:
    init_db()
    engine = get_engine()
    if engine is None:
        print("DATABASE_URL no configurada", file=sys.stderr)
        return 1

    insp = inspect(engine)
    existing = {c["name"] for c in insp.get_columns("tenants")}

    with engine.begin() as conn:
        for name, ddl in _COLUMNS:
            if name in existing:
                print(f"skip {name} (ya existe)")
                continue
            conn.execute(text(f"ALTER TABLE tenants ADD COLUMN {name} {ddl}"))
            print(f"added {name}")

    dispose_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
