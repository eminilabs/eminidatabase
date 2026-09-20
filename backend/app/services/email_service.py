"""Transactional email transport — Resend, or a console backend for dev/tests so
neither needs a real API key. Knows nothing about *what* is being sent; that's
app/services/notification_service.py's job. No Resend SDK: it's a single REST
call, the same pattern as every other outbound HTTP call in this codebase.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("email")

_RESEND_API_URL = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    settings = get_settings()
    if settings.email_backend == "console":
        logger.info("EMAIL to=%s subject=%r\n%s", to, subject, text)
        return
    if settings.email_backend != "resend":
        raise ValueError(f"Unknown email_backend: {settings.email_backend!r}")

    payload: dict = {"from": settings.email_from, "to": [to], "subject": subject, "text": text}
    if html:
        payload["html"] = html
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
        )
    resp.raise_for_status()
