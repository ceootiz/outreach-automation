from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable

from .config import get_gmail_password
from .logger_setup import get_logger, redact_secret


class MailerError(RuntimeError):
    pass


class MailerConfigError(MailerError):
    pass


class MailerSendError(MailerError):
    pass


@dataclass(slots=True)
class ConnectionCheckResult:
    ok: bool
    message: str


class GmailSMTPMailer:
    def __init__(self, password_getter: Callable[..., str] = get_gmail_password):
        self.password_getter = password_getter
        self.logger = get_logger()

    def _password_for(self, sender_email: str, override_password: str | None = None) -> str:
        if override_password is not None:
            return override_password.strip()
        try:
            return str(self.password_getter(sender_email) or "").strip()
        except TypeError:
            return str(self.password_getter() or "").strip()

    @staticmethod
    def _clean_email(value: str, label: str) -> str:
        email = (value or "").strip()
        if not email or "@" not in email or any(char.isspace() for char in email):
            raise MailerConfigError(f"{label} is missing or invalid.")
        return email

    def send_email(
        self,
        host: str,
        port: int,
        sender_email: str,
        recipient_email: str,
        subject: str,
        body: str,
        password: str | None = None,
    ) -> None:
        sender_email = self._clean_email(sender_email, "Sender email")
        recipient_email = self._clean_email(recipient_email, "Recipient email")
        password = self._password_for(sender_email, password)
        if not password:
            raise MailerConfigError(
                "Gmail app password is missing. Save it in Email settings or configure .env for development."
            )

        message = EmailMessage()
        message["From"] = sender_email
        message["To"] = recipient_email
        message["Subject"] = subject or "(no subject)"
        message.set_content(body or "")

        try:
            with smtplib.SMTP(host, int(port), timeout=30) as smtp:
                smtp.starttls()
                smtp.login(sender_email, password)
                smtp.sendmail(sender_email, [recipient_email], message.as_string())
        except MailerConfigError:
            raise
        except Exception as exc:
            sanitized = redact_secret(exc, extra_secrets=[password])
            self.logger.error("SMTP send failed: %s", sanitized)
            raise MailerSendError(f"SMTP send failed: {sanitized}") from exc

    def check_connection(
        self,
        host: str,
        port: int,
        sender_email: str,
        password: str | None = None,
    ) -> ConnectionCheckResult:
        if not host:
            return ConnectionCheckResult(False, "SMTP host is missing in Settings.")
        if not port:
            return ConnectionCheckResult(False, "SMTP port is missing in Settings.")
        if not sender_email:
            return ConnectionCheckResult(False, "Sender email is missing in Settings.")

        password = self._password_for(sender_email, password)
        if not password:
            return ConnectionCheckResult(
                False,
                "Gmail app password is missing. Save it in Email settings or configure .env for development.",
            )

        try:
            with smtplib.SMTP(host, int(port), timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(sender_email, password)
        except smtplib.SMTPAuthenticationError as exc:
            sanitized = redact_secret(exc, extra_secrets=[password])
            self.logger.error("Gmail authentication failed: %s", sanitized)
            return ConnectionCheckResult(
                False,
                "Invalid credentials or Gmail blocked login. Check Gmail address and App Password.",
            )
        except smtplib.SMTPException as exc:
            sanitized = redact_secret(exc, extra_secrets=[password])
            self.logger.error("Gmail SMTP error: %s", sanitized)
            return ConnectionCheckResult(False, f"SMTP error: {sanitized}")
        except Exception as exc:
            sanitized = redact_secret(exc, extra_secrets=[password])
            self.logger.error("Gmail connection check failed: %s", sanitized)
            return ConnectionCheckResult(False, f"Gmail connection check failed: {sanitized}")

        return ConnectionCheckResult(True, "Connected. Gmail SMTP login succeeded. No email was sent.")
