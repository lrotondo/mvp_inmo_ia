from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def require_onboarding_bearer(authorization: str | None = Header(None)) -> None:
    secret = os.environ.get("ONBOARDING_API_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="ONBOARDING_API_SECRET no configurado en el servidor",
        )
    received = (authorization or "").strip()
    expected = f"Bearer {secret}"
    if not received or not hmac.compare_digest(received, expected):
        raise HTTPException(status_code=401, detail="No autorizado")
