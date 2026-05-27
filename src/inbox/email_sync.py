from __future__ import annotations

import email
import imaplib
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from typing import Protocol

from ..logger_setup import redact_secret


@dataclass(frozen=True, slots=True)
class EmailReplyMessage:
    imap_uid: str
    remote_message_id: str
    sender_email: str
    sender_name: str
    subject: str
    body: str
    in_reply_to: str = ""
    references: str = ""
    received_at: str = ""


class EmailSyncClientProtocol(Protocol):
    def fetch_since(self, *, username: str, password: str, last_uid: str = "", limit: int = 25) -> list[EmailReplyMessage]:
        ...


class EmailSyncClient:
    """Read-only Gmail IMAP client.

    The client selects INBOX with readonly=True and only fetches message data.
    It does not delete, archive, flag, or mark messages read remotely.
    """

    def __init__(self, host: str = "imap.gmail.com", port: int = 993, timeout: int = 20):
        self.host = host
        self.port = port
        self.timeout = timeout

    def fetch_since(
        self,
        *,
        username: str,
        password: str,
        last_uid: str = "",
        limit: int = 25,
    ) -> list[EmailReplyMessage]:
        if not username.strip():
            raise RuntimeError("IMAP sync requires an active Gmail profile.")
        if not password:
            raise RuntimeError("IMAP sync requires saved Gmail App Password.")
        mailbox = imaplib.IMAP4_SSL(self.host, self.port, timeout=self.timeout)
        try:
            mailbox.login(username, password)
            mailbox.select("INBOX", readonly=True)
            start_uid = self._next_uid(last_uid)
            status, data = mailbox.uid("search", None, f"UID {start_uid}:*")
            if status != "OK":
                raise RuntimeError("IMAP search failed.")
            raw_uids = data[0].split() if data and data[0] else []
            uids = raw_uids[-max(limit, 1) :]
            messages: list[EmailReplyMessage] = []
            for uid_bytes in uids:
                uid = uid_bytes.decode("ascii", errors="ignore")
                status, fetch_data = mailbox.uid("fetch", uid, "(RFC822)")
                if status != "OK":
                    continue
                raw_message = self._extract_fetch_payload(fetch_data)
                if not raw_message:
                    continue
                parsed = email.message_from_bytes(raw_message)
                messages.append(self._parse_message(uid, parsed))
            return messages
        except Exception as exc:
            raise RuntimeError(redact_secret(exc, extra_secrets=[password])) from exc
        finally:
            try:
                mailbox.close()
            except Exception:
                pass
            try:
                mailbox.logout()
            except Exception:
                pass

    @staticmethod
    def _next_uid(last_uid: str) -> str:
        try:
            return str(max(int(last_uid or "0") + 1, 1))
        except ValueError:
            return "1"

    @staticmethod
    def _extract_fetch_payload(fetch_data) -> bytes:
        for item in fetch_data or []:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                return item[1]
        return b""

    def _parse_message(self, uid: str, message: Message) -> EmailReplyMessage:
        sender_name, sender_email = self._parse_sender(message.get("From", ""))
        subject = self._decode_header(message.get("Subject", ""))
        body = self._body_text(message)
        received_at = ""
        if message.get("Date"):
            try:
                received_at = parsedate_to_datetime(message.get("Date", "")).replace(microsecond=0).isoformat(sep=" ")
            except Exception:
                received_at = ""
        return EmailReplyMessage(
            imap_uid=uid,
            remote_message_id=self._normalize_message_id(message.get("Message-ID", "")),
            sender_email=sender_email.lower(),
            sender_name=sender_name,
            subject=subject,
            body=body,
            in_reply_to=self._normalize_message_id(message.get("In-Reply-To", "")),
            references=message.get("References", "") or "",
            received_at=received_at,
        )

    @staticmethod
    def _parse_sender(value: str) -> tuple[str, str]:
        parsed = getaddresses([value])
        if not parsed:
            return "", ""
        name, address = parsed[0]
        return str(name or "").strip(), str(address or "").strip()

    @staticmethod
    def _decode_header(value: str) -> str:
        if not value:
            return ""
        try:
            return str(make_header(decode_header(value))).strip()
        except Exception:
            return value.strip()

    @classmethod
    def _body_text(cls, message: Message) -> str:
        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition") or "").lower()
                if content_type == "text/plain" and "attachment" not in disposition:
                    return cls._decode_payload(part)
            for part in message.walk():
                if part.get_content_type() == "text/html":
                    return cls._decode_payload(part)
            return ""
        return cls._decode_payload(message)

    @staticmethod
    def _decode_payload(message: Message) -> str:
        payload = message.get_payload(decode=True)
        if payload is None:
            raw = message.get_payload()
            return str(raw or "").strip()
        charset = message.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()

    @staticmethod
    def _normalize_message_id(value: str) -> str:
        return value.strip().strip("<>").strip()
