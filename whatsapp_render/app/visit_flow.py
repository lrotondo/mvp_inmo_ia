from __future__ import annotations

import re
from typing import Any

from app.capture_flow import clear_bot_offered_visit
from app.waitlist_flow import user_affirms_waitlist_consent

_DECLINE_VISIT_RE = re.compile(
    r"\b("
    r"no\s+quiero|no,?\s*no|mejor\s+no|cancelar|cancel[aá]|"
    r"no\s+por\s+ahora|no\s+necesito|no\s+gracias|"
    r"dej[aá]|olvidate|paso|no\s+me\s+interesa"
    r")\b",
    re.I,
)

_SCHEDULE_SUBSTANTIVE_RE = re.compile(
    r"\b("
    r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|"
    r"entre\s+semana|fin\s+de\s+semana|"
    r"ma[nñ]ana|tarde|noche|horario|"
    r"\d{1,2}\s*(?:hs|h\b|:\d{2})|"
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre|"
    r"sin\s+horario|sin\s+preferencia|cuando\s+puedan|a\s+la\s+brevedad"
    r")\b",
    re.I,
)

_VISIT_PENDING_KEY = "visit_pending"
_VISIT_PROMPT_SENT_KEY = "visit_prompt_sent"
_VISIT_ANSWERED_KEY = "visit_answered"
_VISIT_SCHEDULE_RAW_KEY = "visit_schedule_raw"
_VISIT_INTEREST_TEXT_KEY = "visit_interest_text"
_VISIT_PROPERTY_REF_KEY = "visit_property_ref"


def get_visit_pending(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_VISIT_PENDING_KEY))


def get_visit_prompt_sent(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_VISIT_PROMPT_SENT_KEY))


def get_visit_answered(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_VISIT_ANSWERED_KEY))


def get_visit_schedule_raw(capture_data: dict[str, Any] | None) -> str:
    return str((capture_data or {}).get(_VISIT_SCHEDULE_RAW_KEY) or "").strip()


def get_visit_interest_text(capture_data: dict[str, Any] | None) -> str:
    return str((capture_data or {}).get(_VISIT_INTEREST_TEXT_KEY) or "").strip()


def get_visit_property_ref(capture_data: dict[str, Any] | None) -> str:
    return str((capture_data or {}).get(_VISIT_PROPERTY_REF_KEY) or "").strip()


def is_visit_collecting(capture_data: dict[str, Any] | None) -> bool:
    return get_visit_pending(capture_data) and not get_visit_answered(capture_data)


def reset_visit_state(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = clear_bot_offered_visit(dict(capture_data))
    merged[_VISIT_PENDING_KEY] = False
    merged[_VISIT_PROMPT_SENT_KEY] = False
    merged[_VISIT_ANSWERED_KEY] = False
    merged.pop(_VISIT_SCHEDULE_RAW_KEY, None)
    merged.pop(_VISIT_INTEREST_TEXT_KEY, None)
    merged.pop(_VISIT_PROPERTY_REF_KEY, None)
    return merged


def mark_visit_pending(
    capture_data: dict[str, Any],
    *,
    interest_text: str,
    property_ref: str = "",
) -> dict[str, Any]:
    merged = clear_bot_offered_visit(dict(capture_data))
    merged[_VISIT_PENDING_KEY] = True
    merged[_VISIT_PROMPT_SENT_KEY] = False
    merged[_VISIT_ANSWERED_KEY] = False
    merged.pop(_VISIT_SCHEDULE_RAW_KEY, None)
    merged[_VISIT_INTEREST_TEXT_KEY] = (interest_text or "").strip()
    ref = (property_ref or "").strip()
    if ref:
        merged[_VISIT_PROPERTY_REF_KEY] = ref
    else:
        merged.pop(_VISIT_PROPERTY_REF_KEY, None)
    return merged


def mark_visit_prompt_sent(capture_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_VISIT_PROMPT_SENT_KEY] = True
    return merged


def mark_visit_answered(capture_data: dict[str, Any], user_text: str) -> dict[str, Any]:
    merged = dict(capture_data)
    merged[_VISIT_ANSWERED_KEY] = True
    merged[_VISIT_SCHEDULE_RAW_KEY] = (user_text or "").strip()
    return merged


def user_declines_visit(user_text: str) -> bool:
    body = (user_text or "").strip()
    if not body:
        return False
    if user_affirms_waitlist_consent(body) and len(body) <= 16:
        return False
    return bool(_DECLINE_VISIT_RE.search(body))


def visit_schedule_message_is_substantive(user_text: str) -> bool:
    """Horarios/días o salida explícita (sin horario); no rechazos ni afirmaciones vacías."""
    body = (user_text or "").strip()
    if not body or user_declines_visit(body):
        return False
    if user_affirms_waitlist_consent(body) and len(body) <= 20:
        return False
    if _SCHEDULE_SUBSTANTIVE_RE.search(body):
        return True
    return len(body) >= 28
