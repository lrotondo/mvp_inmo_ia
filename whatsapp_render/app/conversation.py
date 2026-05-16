from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Literal

from sqlalchemy import select

from app.db import get_engine, session_scope
from app.models import ChatMessage

logger = logging.getLogger(__name__)

Role = Literal["user", "assistant"]

# Hasta 5 turnos (user+assistant) = 10 mensajes previos al actual.
_DEFAULT_MAX_MESSAGES = 10
_memory_lock = Lock()
_memory: dict[tuple[str, str], deque[tuple[Role, str]]] = {}


def _max_history_messages() -> int:
    raw = os.environ.get("CHAT_HISTORY_MAX_MESSAGES", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return _DEFAULT_MAX_MESSAGES


@dataclass(frozen=True)
class HistoryTurn:
    role: Role
    content: str


def _memory_key(phone_number_id: str, wa_id: str) -> tuple[str, str]:
    return phone_number_id.strip(), wa_id.strip()


def get_conversation_history(
    phone_number_id: str,
    wa_id: str,
    *,
    limit: int | None = None,
) -> list[HistoryTurn]:
    cap = limit if limit is not None else _max_history_messages()
    pnid = phone_number_id.strip()
    wid = wa_id.strip()
    if not pnid or not wid:
        return []

    if get_engine() is not None:
        with session_scope() as session:
            stmt = (
                select(ChatMessage.role, ChatMessage.content)
                .where(
                    ChatMessage.phone_number_id == pnid,
                    ChatMessage.wa_id == wid,
                )
                .order_by(ChatMessage.created_at.desc())
                .limit(cap)
            )
            rows = list(session.execute(stmt).all())
        out: list[HistoryTurn] = []
        for role, content in reversed(rows):
            if role == "user":
                out.append(HistoryTurn(role="user", content=content))
            elif role == "assistant":
                out.append(HistoryTurn(role="assistant", content=content))
        return out

    key = _memory_key(pnid, wid)
    with _memory_lock:
        items = list(_memory.get(key, deque()))
    return [HistoryTurn(role=role, content=content) for role, content in items[-cap:]]


def append_conversation_turn(
    phone_number_id: str,
    wa_id: str,
    user_text: str,
    assistant_text: str,
) -> None:
    pnid = phone_number_id.strip()
    wid = wa_id.strip()
    user_body = user_text.strip()
    assistant_body = assistant_text.strip()
    if not pnid or not wid or not user_body or not assistant_body:
        return

    cap = _max_history_messages()

    if get_engine() is not None:
        with session_scope() as session:
            session.add(
                ChatMessage(
                    phone_number_id=pnid,
                    wa_id=wid,
                    role="user",
                    content=user_body,
                )
            )
            session.add(
                ChatMessage(
                    phone_number_id=pnid,
                    wa_id=wid,
                    role="assistant",
                    content=assistant_body,
                )
            )
            _trim_db_history(session, pnid, wid, cap)
        return

    key = _memory_key(pnid, wid)
    with _memory_lock:
        bucket = _memory.setdefault(key, deque(maxlen=cap))
        bucket.append(("user", user_body))
        bucket.append(("assistant", assistant_body))


def _trim_db_history(session, phone_number_id: str, wa_id: str, cap: int) -> None:
    stmt = (
        select(ChatMessage.id)
        .where(
            ChatMessage.phone_number_id == phone_number_id,
            ChatMessage.wa_id == wa_id,
        )
        .order_by(ChatMessage.created_at.desc())
    )
    ids = [row[0] for row in session.execute(stmt).all()]
    excess = ids[cap:]
    if not excess:
        return
    for msg_id in excess:
        row = session.get(ChatMessage, msg_id)
        if row is not None:
            session.delete(row)


def format_user_message(text: str) -> str:
    return f"Consulta del cliente: {text.strip()}"


def format_history_plain(history: list[HistoryTurn]) -> str:
    lines: list[str] = []
    for turn in history:
        label = "Cliente" if turn.role == "user" else "Asesor"
        lines.append(f"{label}: {turn.content}")
    return "\n".join(lines)


def build_model_messages(
    system_prompt: str,
    history: list[HistoryTurn],
    current_user_text: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
    ]
    for turn in history:
        if turn.role == "user":
            messages.append(
                {"role": "user", "content": format_user_message(turn.content)}
            )
        else:
            messages.append({"role": "assistant", "content": turn.content})
    messages.append(
        {"role": "user", "content": format_user_message(current_user_text)}
    )
    return messages


# Alias por compatibilidad
build_groq_messages = build_model_messages
