from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool((os.environ.get("SMTP_HOST") or "").strip())


def _smtp_use_tls() -> bool:
    raw = (os.environ.get("SMTP_USE_TLS") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _smtp_port() -> int:
    raw = (os.environ.get("SMTP_PORT") or "587").strip()
    try:
        return int(raw)
    except ValueError:
        return 587


def _send_email_sync(*, to: str, subject: str, body_text: str) -> None:
    host = (os.environ.get("SMTP_HOST") or "").strip()
    if not host:
        raise RuntimeError("SMTP_HOST not configured")

    from_addr = (os.environ.get("SMTP_FROM") or "").strip()
    if not from_addr:
        raise RuntimeError("SMTP_FROM not configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(body_text)

    user = (os.environ.get("SMTP_USER") or "").strip()
    password = (os.environ.get("SMTP_PASSWORD") or "").strip()
    port = _smtp_port()
    use_tls = _smtp_use_tls()

    if use_tls:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)


async def send_email(*, to: str, subject: str, body_text: str) -> None:
    recipient = (to or "").strip()
    if not recipient:
        raise ValueError("email recipient required")
    if not smtp_configured():
        logger.warning("SMTP no configurado; omitiendo envio de email a %s", recipient)
        return
    await asyncio.to_thread(
        _send_email_sync,
        to=recipient,
        subject=subject,
        body_text=body_text,
    )
    logger.info("Email enviado a %s subject=%r", recipient, subject[:80])
