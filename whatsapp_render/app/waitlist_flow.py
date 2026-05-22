from __future__ import annotations

from typing import Any

_WAITLIST_PENDING_KEY = "waitlist_pending"
_WAITLIST_PROMPT_SENT_KEY = "waitlist_prompt_sent"
_WAITLIST_ANSWERED_KEY = "waitlist_answered"
_WAITLIST_RAW_TEXT_KEY = "waitlist_raw_text"


def get_waitlist_pending(capture_data: dict[str, Any] | None) -> bool:
    return bool((capture_data or {}).get(_WAITLIST_PENDING_KEY))


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
    merged[_WAITLIST_PROMPT_SENT_KEY] = False
    merged[_WAITLIST_ANSWERED_KEY] = False
    merged.pop(_WAITLIST_RAW_TEXT_KEY, None)
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
