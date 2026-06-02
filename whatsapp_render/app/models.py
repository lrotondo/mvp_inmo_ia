from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
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
    catalog_rent_csv_path = mapped_column(String(512), nullable=True)
    waba_id = mapped_column(String(64), nullable=True, index=True)
    business_portfolio_id = mapped_column(String(64), nullable=True)
    onboarding_status = mapped_column(String(32), nullable=False, default="manual")
    onboarding_error = mapped_column(Text, nullable=True)
    connected_at = mapped_column(DateTime(timezone=True), nullable=True)
    token_expires_at = mapped_column(DateTime(timezone=True), nullable=True)
    platform_tenant_id = mapped_column(Integer, nullable=True, index=True)
    lead_alert_email = mapped_column(String(255), nullable=True)
    lead_alert_whatsapp_to = mapped_column(String(32), nullable=True)
    lead_notify_email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    lead_notify_whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    office_hours = mapped_column(Text, nullable=True)
    office_address = mapped_column(Text, nullable=True)
    social_links = mapped_column(Text, nullable=True)


class OnboardingSession(Base):
    __tablename__ = "onboarding_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invite_token = mapped_column(String(64), nullable=True, unique=True, index=True)
    status = mapped_column(String(32), nullable=False, default="pending")
    waba_id = mapped_column(String(64), nullable=True, index=True)
    phone_number_id = mapped_column(String(64), nullable=True, index=True)
    business_portfolio_id = mapped_column(String(64), nullable=True)
    tenant_id = mapped_column(Integer, nullable=True)
    platform_tenant_id = mapped_column(Integer, nullable=True, index=True)
    error_message = mapped_column(Text, nullable=True)
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


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint("phone_number_id", "wa_id", name="uq_chat_session"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    flow_path: Mapped[str] = mapped_column(String(32), nullable=False, default="nuevo")
    bot_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    capture_data = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


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
    lead_type = mapped_column(String(32), nullable=False, default="venta")
    capture_summary = mapped_column(Text, nullable=True)
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


class ClientWaitlist(Base):
    __tablename__ = "client_waitlist"
    __table_args__ = (
        UniqueConstraint(
            "phone_number_id",
            "wa_id",
            "seek_type",
            "status",
            name="uq_client_waitlist_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    contact_name = mapped_column(String(255), nullable=True)
    seek_type = mapped_column(String(32), nullable=False)
    status = mapped_column(String(32), nullable=False, default="active")
    requirements_json = mapped_column(Text, nullable=False)
    requirements_summary = mapped_column(Text, nullable=False)
    conversation_summary = mapped_column(Text, nullable=False)
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
