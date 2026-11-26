"""Email the Coltek team about new leads and demo requests via Resend or SMTP."""
import logging
import smtplib
from email.message import EmailMessage

import httpx

from chatbot.config import settings

logger = logging.getLogger(__name__)


def _recipients() -> list[str]:
    # NOTIFY_EMAIL_TO is the explicit destination. EMAIL_ADDRESS remains a
    # compatible fallback for the old single-mailbox SMTP setup.
    value = settings.notify_email_to or settings.smtp_user
    return [address.strip() for address in value.split(",") if address.strip()]


def smtp_configured() -> bool:
    return bool(settings.smtp_host and _recipients())


def resend_configured() -> bool:
    return bool(settings.resend_api_key and settings.default_from_email and settings.notify_email_to)


def _notify_resend(subject: str, body: str) -> bool:
    if not resend_configured():
        missing = []
        if not settings.resend_api_key:
            missing.append("RESEND_API_KEY")
        if not settings.default_from_email:
            missing.append("DEFAULT_FROM_EMAIL")
        if not settings.notify_email_to:
            missing.append("NOTIFY_EMAIL_TO")
        logger.warning("Resend not configured (%s missing); team not emailed", ", ".join(missing))
        return False

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.default_from_email,
                "to": [address.strip() for address in settings.notify_email_to.split(",") if address.strip()],
                "subject": subject,
                "text": body,
            },
            timeout=15,
        )
        response.raise_for_status()
        return True
    except Exception:
        # Never log message contents, which include visitor contact details.
        logger.warning("Could not email the team through Resend", exc_info=True)
        return False


def _notify_smtp(subject: str, body: str) -> bool:
    recipients = _recipients()
    if not settings.smtp_host or not recipients:
        missing = []
        if not settings.smtp_host:
            missing.append("EMAIL_SMTP_SERVER (or SMTP_HOST)")
        if not recipients:
            missing.append("NOTIFY_EMAIL_TO (or EMAIL_ADDRESS)")
        logger.warning("SMTP not configured (%s missing); team not emailed", ", ".join(missing))
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        return True
    except Exception:
        logger.warning("Could not email the team (SMTP error)", exc_info=True)
        return False


def notify_team(subject: str, body: str) -> bool:
    """Notify the team; email failures never lose the saved lead or break chat."""
    backend = settings.email_backend.strip().lower()
    if backend in {"resend", "anymail.backends.resend.emailbackend"}:
        return _notify_resend(subject, body)
    if backend == "smtp":
        return _notify_smtp(subject, body)
    logger.warning("Unsupported EMAIL_BACKEND value; team not emailed")
    return False
