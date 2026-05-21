"""Crea tablas según DATABASE_URL (MySQL o Postgres). Uso: python -m app.sync_db"""

from __future__ import annotations

import sys

from sqlalchemy import inspect

from app import models  # noqa: F401 — registra modelos en Base.metadata
from app.db import get_engine, init_db


def main() -> None:
    engine = init_db()
    if engine is None:
        print("Error: define DATABASE_URL antes de ejecutar.", file=sys.stderr)
        sys.exit(1)

    tables = sorted(inspect(engine).get_table_names())
    print("Tablas:", ", ".join(tables))
    print("Listo.")


if __name__ == "__main__":
    main()
