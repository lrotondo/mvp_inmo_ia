from __future__ import annotations

import hmac
import os
import re
from hashlib import sha256


def _normalize_meta_app_secret(raw: str) -> str:
    """Quita espacios, saltos de linea y comillas tipicas al pegar en Render."""
    s = (raw or "").strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    return s


def should_skip_meta_signature() -> bool:
    return os.environ.get("META_SKIP_SIGNATURE", "").strip() in ("1", "true", "True")


def validate_meta_verify_token(received: str) -> bool:
    expected = os.environ.get("META_VERIFY_TOKEN", "").strip()
    if not expected:
        return False
    return hmac.compare_digest(received.strip(), expected)


def validate_meta_signature(raw_body: bytes, signature_header: str) -> bool:
    if should_skip_meta_signature():
        return True

    app_secret = _normalize_meta_app_secret(os.environ.get("META_APP_SECRET", ""))
    if not app_secret:
        return False

    value = (signature_header or "").strip()
    if not value:
        return False

    match = re.match(r"(?i)sha256=(.+)", value)
    if match:
        value = match.group(1).strip()

    # Solo hex (Meta manda 64 chars hex en SHA-256)
    if not re.fullmatch(r"[0-9a-fA-F]+", value):
        return False

    expected_hex = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        sha256,
    ).hexdigest()
    return hmac.compare_digest(value.lower(), expected_hex.lower())
