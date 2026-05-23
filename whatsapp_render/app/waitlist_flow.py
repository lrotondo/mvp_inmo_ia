from __future__ import annotations

import re
from typing import Any

_WAITLIST_PENDING_KEY = "waitlist_pending"
_WAITLIST_CONSENT_SENT_KEY = "waitlist_consent_sent"
_WAITLIST_PROMPT_SENT_KEY = "waitlist_prompt_sent"
_WAITLIST_ANSWERED_KEY = "waitlist_answered"
_WAITLIST_RAW_TEXT_KEY = "waitlist_raw_text"

_AFFIRM_CONSENT_RE = re.compile(
    r"^(?:"
    r"s[ií]|dale|ok(?:ay)?|de\s+acuerdo|perfecto|"
    r"bueno|genial|claro|por\s+supuesto|obvio|"
    r"me\s+interesa|acepto|avancemos"
    r")[\s!.?]*$",
    re.I,
)


def get_waitlist_pending(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_WAITLIST_PENDING_KEY))


def get_waitlist_consent_sent(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_WAITLIST_CONSENT_SENT_KEY))


def get_waitlist_prompt_sent(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_WAITLIST_PROMPT_SENT_KEY))


def get_waitlist_answered(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_WAITLIST_ANSWERED_KEY))


def get_waitlist_raw_text(capture_data: dict[str, Any] | None) -> str:
    return str((capture_data or {}).get(_WAITLIST_RAW_TEXT_KEY) or "").strip()


def is_waitlist_collecting(capture_data: dict[str, Any] | None) -> bool:
    return get_waitlist_pending(capture_data) and not get_waitlist_answered(capture_data)


def reset_waitlist_state(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_WAITLIST_PENDING_KEY] = False
    merged[_WAITLIST_CONSENT_SENT_KEY] = False
    merged[_WAITLIST_PROMPT_SENT_KEY] = False
    merged[_WAITLIST_ANSWERED_KEY] = False
    merged.pop(_WAITLIST_RAW_TEXT_KEY, None)
    return merged


def user_affirms_waitlist_consent(user_text: str) -> bool:
    return bool(_AFFIRM_CONSENT_RE.match((user_text or "").strip()))


def waitlist_message_is_substantive(user_text: str) -> bool:
    """Requisitos completos en un mensaje (no solo afirmación corta)."""
    body = (user_text or "").strip()
    if len(body) < 24:
        return False
    if user_affirms_waitlist_consent(body):
        return False
    return bool(
        re.search(
            r"\b("
            r"dormitorio|ambiente|pileta|tenis|zona|barrio|presupuesto|"
            r"usd|metros|m2|casa|departamento|lote|terreno|mascota"
            r")\b",
            body,
            re.I,
        )
    )


def mark_waitlist_consent_sent(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_WAITLIST_CONSENT_SENT_KEY] = True
    return merged


def mark_waitlist_pending(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_WAITLIST_PENDING_KEY] = True
    return merged


def mark_waitlist_prompt_sent(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_WAITLIST_PROMPT_SENT_KEY] = True
    return merged


def mark_waitlist_answered(capture_data: dict[str, Any], user_text: str) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_WAITLIST_ANSWERED_KEY] = True
    merged[_WAITLIST_RAW_TEXT_KEY] = (user_text or "").strip()
    return merged
