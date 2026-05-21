from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _normalize_database_url(url: str) -> str:
    """Normaliza DATABASE_URL para SQLAlchemy (MySQL o Postgres legacy)."""
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)
    if url.startswith("mysql+pymysql://"):
        if "charset=" not in url:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}charset=utf8mb4"
        return url
    scheme = url.split("://", 1)[0]
    if "+psycopg" in scheme:
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _engine_kwargs(url: str) -> dict:
    if url.startswith("mysql"):
        return {
            "pool_pre_ping": True,
            "pool_size": 5,
            "max_overflow": 2,
        }
    return {"pool_pre_ping": True}


def get_engine() -> Engine | None:
    global _engine
    if _engine is not None:
        return _engine
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        return None
    url = _normalize_database_url(raw)
    _engine = create_engine(url, **_engine_kwargs(url))
    return _engine


def get_session_factory() -> sessionmaker[Session] | None:
    global _SessionLocal
    engine = get_engine()
    if engine is None:
        return None
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SessionLocal


def init_db() -> Engine | None:
    engine = get_engine()
    if engine is None:
        logger.info(
            "DATABASE_URL no definida: modo sin base de datos (solo fallback META_*)."
        )
        return None
    Base.metadata.create_all(bind=engine)
    logger.info("Tablas SQLAlchemy sincronizadas (create_all).")
    return engine


def dispose_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionLocal = None


@contextmanager
def session_scope() -> Iterator[Session]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL no configurada")
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
