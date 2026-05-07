from __future__ import annotations

import hmac
import os
from hashlib import sha256


def validate_meta_verify_token(received: str) -> bool:
    expected = os.environ.get("META_VERIFY_TOKEN", "").strip()
    if not expected:
        return False
    return hmac.compare_digest(received.strip(), expected)


def validate_meta_signature(raw_body: bytes, signature_header: str) -> bool:
    app_secret = os.environ.get("META_APP_SECRET", "").strip()
    if not app_secret:
        return False

    value = signature_header.strip()
    if not value:
        return False

    prefix = "sha256="
    if value.startswith(prefix):
        value = value[len(prefix) :]

    expected_hex = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        sha256,
    ).hexdigest()
    return hmac.compare_digest(value.lower(), expected_hex.lower())
