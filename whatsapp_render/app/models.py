from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
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


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ClientLead(Base):
    __tablename__ = "client_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    contact_name = mapped_column(String(255), nullable=True)
    property_ref = mapped_column(String(512), nullable=True)
    interest_summary = mapped_column(Text, nullable=False)
    conversation_summary = mapped_column(Text, nullable=False)
    conversation_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
