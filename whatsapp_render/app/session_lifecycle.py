from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.session_state import SessionState

logger = logging.getLogger(__name__)

_LAST_INBOUND_AT_KEY = "last_inbound_at"
_ADVISOR_HANDOFF_COMPLETED_AT_KEY = "advisor_handoff_completed_at"

_INITIAL_GREETING_RE = re.compile(
    r"^\s*("
    r"hola|holaa|holaaa|hey|hi|"
    r"buen(?:os|as)?\s+d[ií]as?|"
    r"buen(?:os|as)?\s+tardes?|"
    r"buen(?:os|as)?\s+noches?|"
    r"buenas|"
    r"qu[eé]\s+tal|"
    r"saludos"
    r")\b",
    re.I,
)

_FLOW_INTENT_AFTER_GREETING_RE = re.compile(
    r"\b("
    r"comprar|compra|alquilar|alquiler|vender|vendo|captaci[oó]n|"
    r"opci[oó]n|opciones|propiedad|departamento|depto|casa|lote|"
    r"visita|asesor|humano|busco|quiero|necesito|"
    r"m[aá]s\s+opciones|ninguna\s+sirve|lista\s+de\s+espera"
    r")\b",
    re.I,
)

_LISTING_PICK_RE = re.compile(
    r"\b(?:la|el)\s+opci[oó]n\s*\d+|opci[oó]n\s*\d+\b",
    re.I,
)


def _idle_restart_hours() -> float:
    raw = os.environ.get("SESSION_IDLE_RESTART_HOURS", "").strip()
    if not raw:
        return 24.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 24.0


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_initial_greeting(text: str) -> bool:
    """True si el mensaje es principalmente un saludo, sin intención de flujo."""
    body = (text or "").strip()
    if not body:
        return False
    if not _INITIAL_GREETING_RE.search(body):
        return False
    remainder = _INITIAL_GREETING_RE.sub("", body, count=1).strip(" \t\n\r.,!?¡¿…-")
    if not remainder:
        return True
    if _FLOW_INTENT_AFTER_GREETING_RE.search(remainder):
        return False
    if _LISTING_PICK_RE.search(remainder):
        return False
    return len(remainder) <= 12


def get_last_inbound_at(
    capture_data: dict[str, Any] | None,
    session_updated_at: datetime | None,
) -> datetime | None:
    raw = (capture_data or {}).get(_LAST_INBOUND_AT_KEY)
    parsed = _parse_iso_datetime(raw)
    if parsed is not None:
        return parsed
    if session_updated_at is not None:
        return _parse_iso_datetime(session_updated_at)
    return None


def is_session_idle_over_threshold(
    last_inbound_at: datetime | None,
    *,
    now: datetime | None = None,
    hours: float | None = None,
) -> bool:
    if last_inbound_at is None:
        return False
    threshold_hours = _idle_restart_hours() if hours is None else hours
    if threshold_hours <= 0:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current - last_inbound_at > timedelta(hours=threshold_hours)


def had_advisor_handoff(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_ADVISOR_HANDOFF_COMPLETED_AT_KEY))


def should_auto_restart_session(
    capture_data: dict[str, Any] | None,
    user_text: str,
    last_inbound_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    if not is_initial_greeting(user_text):
        return False
    idle = is_session_idle_over_threshold(last_inbound_at, now=now)
    handoff = had_advisor_handoff(capture_data)
    if idle or handoff:
        logger.info(
            "auto_restart_session idle=%s handoff=%s text=%r",
            idle,
            handoff,
            (user_text or "")[:80],
        )
        return True
    return False


def apply_session_restart() -> SessionState:
    return SessionState(flow_path="nuevo", bot_paused=False, capture_data={})


def mark_advisor_handoff_completed(
    capture_data: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    merged = dict(capture_data or {})
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    merged[_ADVISOR_HANDOFF_COMPLETED_AT_KEY] = current.isoformat()
    return merged


def touch_last_inbound_at(
    capture_data: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    merged = dict(capture_data or {})
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    merged[_LAST_INBOUND_AT_KEY] = current.isoformat()
    return merged
