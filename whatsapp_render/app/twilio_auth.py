from __future__ import annotations

import os
from typing import Iterable, Mapping

from twilio.request_validator import RequestValidator


def should_skip_validation() -> bool:
    return os.environ.get("SKIP_TWILIO_SIGNATURE", "").strip() in ("1", "true", "True")


def validate_twilio_signature_any(
    candidate_urls: Iterable[str], form: Mapping[str, str], signature: str
) -> bool:
    if should_skip_validation():
        return True

    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    if not token or not signature:
        return False

    validator = RequestValidator(token)
    params = dict(form)
    seen: set[str] = set()
    for raw_url in candidate_urls:
        url = raw_url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        if validator.validate(url, params, signature):
            return True
    return False
