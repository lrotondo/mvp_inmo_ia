from __future__ import annotations

import os
from typing import Dict, Mapping

from twilio.request_validator import RequestValidator


def should_skip_validation() -> bool:
    return os.environ.get("SKIP_TWILIO_SIGNATURE", "").strip() in ("1", "true", "True")


def validate_twilio_signature(public_url: str, form: Mapping[str, str], signature: str) -> bool:
    if should_skip_validation():
        return True

    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    if not token:
        return False

    validator = RequestValidator(token)
    params = dict(form)
    return bool(validator.validate(public_url, params, signature))
