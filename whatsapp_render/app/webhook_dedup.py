from __future__ import annotations

import logging
import time
from threading import Lock

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 86_400
_lock = Lock()
_seen_message_ids: dict[str, float] = {}


def _ttl_seconds() -> int:
    import os

    raw = os.environ.get("WEBHOOK_DEDUP_TTL_SECONDS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return _DEFAULT_TTL_SECONDS


def _prune(now: float) -> None:
    ttl = _ttl_seconds()
    stale = [key for key, ts in _seen_message_ids.items() if (now - ts) > ttl]
    for key in stale:
        _seen_message_ids.pop(key, None)


def claim_inbound_message_id(message_id: str) -> bool:
    """
    True si este wamid puede procesarse; False si ya fue visto (reintento de Meta).
    """
    mid = (message_id or "").strip()
    if not mid:
        return True

    now = time.monotonic()
    with _lock:
        _prune(now)
        if mid in _seen_message_ids:
            logger.info("Webhook dedup: mensaje ya procesado message_id=%s", mid[:48])
            return False
        _seen_message_ids[mid] = now
        if len(_seen_message_ids) > 10_000:
            oldest = min(_seen_message_ids.items(), key=lambda item: item[1])
            _seen_message_ids.pop(oldest[0], None)
        return True
