from __future__ import annotations

import re
from typing import Any

_USER_FLOW_MESSAGES_KEY = "user_flow_messages"
_MAX_USER_MESSAGES_PER_FLOW = 40

_BOT_ASKED_VISIT_TIME_KEY = "bot_asked_visit_time"

_BOT_ASKED_TIME_PREFERENCE_RE = re.compile(
    r"\b("
    r"ma[nñ]ana|tarde|fin\s+de\s+semana|preferencia\s+general|"
    r"qu[eé]\s+franja|horario\s+prefer"
    r")\b",
    re.I,
)

def user_messages_for_flow(
    current_user_text: str,
    flow_path: str,
    capture_data: dict[str, Any] | None = None,
) -> str:
    """Mensajes del cliente en la rama actual (persistidos en capture_data)."""
    path = (flow_path or "").strip().lower()
    parts: list[str] = []
    raw = (capture_data or {}).get(_USER_FLOW_MESSAGES_KEY)
    if isinstance(raw, dict):
        stored = raw.get(path)
        if isinstance(stored, list):
            parts.extend(str(m).strip() for m in stored if str(m).strip())
    current = current_user_text.strip()
    if current and (not parts or parts[-1] != current):
        parts.append(current)
    return "\n".join(parts)


def append_user_flow_message(
    capture_data: dict[str, Any],
    flow_path: str,
    user_text: str,
) -> dict[str, Any]:
    """Registra el mensaje del cliente al cerrar el turno (sin tabla chat_messages)."""
    merged = dict(capture_data or {})
    text = (user_text or "").strip()
    if not text:
        return merged
    path = (flow_path or "").strip().lower()
    if not path:
        return merged

    raw = merged.get(_USER_FLOW_MESSAGES_KEY)
    if not isinstance(raw, dict):
        raw = {}
    else:
        raw = dict(raw)

    messages = list(raw.get(path) or [])
    if not messages or messages[-1] != text:
        messages.append(text)
    raw[path] = messages[-_MAX_USER_MESSAGES_PER_FLOW:]
    merged[_USER_FLOW_MESSAGES_KEY] = raw
    return merged


def format_user_messages_plain(
    current_user_text: str = "",
    *,
    flow_path: str = "",
    capture_data: dict[str, Any] | None = None,
) -> str:
    if flow_path:
        return user_messages_for_flow(current_user_text, flow_path, capture_data)
    return current_user_text.strip()


def bot_asked_visit_time_preference(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_BOT_ASKED_VISIT_TIME_KEY))


def merge_outbound_capture_flags(
    capture_data: dict[str, Any],
    outbound_text: str,
) -> dict[str, Any]:
    """Marca señales del último mensaje del bot en capture_data."""
    merged = dict(capture_data or {})
    body = (outbound_text or "").strip()
    if not body:
        return merged
    if _BOT_ASKED_TIME_PREFERENCE_RE.search(body):
        merged[_BOT_ASKED_VISIT_TIME_KEY] = True
    return merged
