from __future__ import annotations

from typing import Any

from app.capture_flow import clear_bot_offered_visit

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
