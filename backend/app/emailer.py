"""Sends transactional email over SMTP (works with Resend, Postmark, SendGrid, Gmail,
etc.). Without SMTP settings the message is logged instead, which is handy locally."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger("fomoshi.email")


def _send_sync(to: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        if s.smtp_starttls:
            smtp.starttls()
        if s.smtp_username:
            smtp.login(s.smtp_username, s.smtp_password or "")
        smtp.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> None:
    if not get_settings().smtp_host:
        log.info("Email (SMTP not configured)\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return
    try:
        await asyncio.to_thread(_send_sync, to, subject, body)
    except Exception:
        log.exception("Failed to send email to %s", to)
