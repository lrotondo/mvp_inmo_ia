from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    # Sin Mapped[Optional[...]]: SQLAlchemy 2.0.x + Python 3.14 rompe al parsear unions en anotaciones.
    name = mapped_column(String(255), nullable=True)
    system_prompt = mapped_column(Text, nullable=True)
    catalog_csv_path = mapped_column(String(512), nullable=True)
