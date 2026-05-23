from __future__ import annotations

import logging

from sqlalchemy import delete, func, select

from app.db import session_scope
from app.models import ChatMessage, ChatSession, ClientLead, ClientWaitlist

logger = logging.getLogger(__name__)

_RESET_MODELS: tuple[type, ...] = (
    ChatMessage,
    ChatSession,
    ClientLead,
    ClientWaitlist,
)


def clear_operational_chat_tables() -> dict[str, int]:
    """
    Vacía chat_messages, chat_sessions, client_leads y client_waitlist.
    No toca tenants ni onboarding_sessions.
    """
    deleted: dict[str, int] = {}
    with session_scope() as session:
        for model in _RESET_MODELS:
            table = model.__tablename__
            count_before = session.scalar(
                select(func.count()).select_from(model)
            )
            session.execute(delete(model))
            deleted[table] = int(count_before or 0)
    logger.warning(
        "operational_chat_tables_cleared deleted=%s",
        deleted,
    )
    return deleted
