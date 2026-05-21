from __future__ import annotations

from app.db import _normalize_database_url


def test_normalize_mysql_url() -> None:
    assert _normalize_database_url("mysql://user:pass@host:3306/db") == (
        "mysql+pymysql://user:pass@host:3306/db?charset=utf8mb4"
    )


def test_normalize_mysql_pymysql_keeps_charset() -> None:
    url = "mysql+pymysql://user:pass@host:3306/db?charset=utf8mb4"
    assert _normalize_database_url(url) == url


def test_normalize_postgres_url() -> None:
    assert _normalize_database_url("postgresql://u:p@h/db").startswith(
        "postgresql+psycopg://"
    )


def test_normalize_postgres_short_scheme() -> None:
    assert _normalize_database_url("postgres://u:p@h/db").startswith(
        "postgresql+psycopg://"
    )
