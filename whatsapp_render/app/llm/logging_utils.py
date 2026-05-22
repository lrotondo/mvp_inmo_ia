from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_PREVIEW_LIMIT = 500
_PAYLOAD_JSON_LIMIT = 12_000


def _truncate(text: str, limit: int) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    return body[: limit - 3] + "..."


def log_llm_context(context: dict[str, Any]) -> None:
    logger.info("llm_context %s", json.dumps(context, ensure_ascii=False, default=str))


def log_llm_request(
    payload: dict[str, Any],
    *,
    extra_context: dict[str, Any] | None = None,
) -> None:
    if extra_context:
        log_llm_context(extra_context)

    safe = {
        "model": payload.get("model"),
        "temperature": payload.get("temperature"),
        "max_tokens": payload.get("max_tokens"),
        "stream": payload.get("stream"),
        "message_count": len(payload.get("messages") or []),
    }
    logger.info("llm_request_meta %s", json.dumps(safe, ensure_ascii=False))

    raw = json.dumps(payload, ensure_ascii=False, default=str)
    if len(raw) > _PAYLOAD_JSON_LIMIT:
        logger.info(
            "llm_payload_truncated total_chars=%d\n%s",
            len(raw),
            raw[:_PAYLOAD_JSON_LIMIT] + "…",
        )
    else:
        logger.info("llm_payload %s", raw)

    for index, msg in enumerate(payload.get("messages") or []):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "?")
        content = str(msg.get("content") or "")
        logger.info(
            "llm_message index=%d role=%s chars=%d\n%s",
            index,
            role,
            len(content),
            content,
        )


def log_llm_response(text: str) -> None:
    body = (text or "").strip()
    logger.info(
        "llm_response chars=%d preview=%s",
        len(body),
        _truncate(body, _PREVIEW_LIMIT),
    )
