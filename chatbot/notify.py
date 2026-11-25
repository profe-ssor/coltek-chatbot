"""Email the Coltek team about new leads and demo requests (SMTP settings in .env)."""
import logging
import smtplib
from email.message import EmailMessage

from chatbot.config import settings

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.notify_email_to)


def notify_team(subject: str, body: str) -> bool:
    """Send an email to NOTIFY_EMAIL_TO. Returns True if it was sent.

    Never raises: if SMTP is not configured or sending fails, a warning is logged instead,
    so a mail problem can never lose a lead or break the chat.
    """
    # The subject and body contain the visitor's name and phone number, so they are never logged.
    if not smtp_configured():
        logger.warning("SMTP not configured (SMTP_HOST / NOTIFY_EMAIL_TO empty); team not emailed")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = settings.notify_email_to
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
