from __future__ import annotations

import hashlib
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from leadpilot.application.proposal_email import (
    EmailAttachmentError,
    EmailAuthenticationError,
    EmailPermanentFailureError,
    EmailProviderConfiguration,
    EmailProviderUnavailableError,
    EmailSendRequest,
    EmailSendResult,
    EmailTemporaryFailureError,
    EmailTimeoutError,
)


class FakeEmailProvider:
    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.requests: list[EmailSendRequest] = []

    def send(self, request: EmailSendRequest) -> EmailSendResult:
        self.requests.append(request)
        errors = {
            "authentication_failure": EmailAuthenticationError(
                "Email provider authentication failed."
            ),
            "timeout": EmailTimeoutError("Email provider timed out."),
            "provider_unavailable": EmailProviderUnavailableError(
                "Email provider is temporarily unavailable."
            ),
            "temporary_failure": EmailTemporaryFailureError(
                "Email was temporarily rejected."
            ),
            "permanent_rejection": EmailPermanentFailureError(
                "A recipient was permanently rejected."
            ),
            "attachment_rejection": EmailAttachmentError(
                "The provider rejected the attachment."
            ),
            "provider_failure": EmailPermanentFailureError(
                "The provider could not deliver the message."
            ),
        }
        if self.mode in errors:
            raise errors[self.mode]
        digest = hashlib.sha256(request.idempotency_key.encode()).hexdigest()[:20]
        return EmailSendResult(
            f"fake-{digest}",
            {"accepted_count": len(request.recipients.all), "provider": "FAKE"},
        )


class SMTPEmailProvider:
    def __init__(self, configuration: EmailProviderConfiguration) -> None:
        self._config = configuration

    def send(self, request: EmailSendRequest) -> EmailSendResult:
        if not self._config.smtp_host:
            raise EmailProviderUnavailableError("SMTP is not configured.")
        message = self.build_message(request)
        client_class = smtplib.SMTP_SSL if self._config.use_ssl else smtplib.SMTP
        try:
            with client_class(
                self._config.smtp_host,
                self._config.smtp_port,
                timeout=self._config.timeout_seconds,
            ) as client:
                if self._config.use_tls:
                    client.starttls()
                if self._config.smtp_username:
                    client.login(
                        self._config.smtp_username, self._config.smtp_password or ""
                    )
                refused = client.send_message(
                    message, to_addrs=list(request.recipients.all)
                )
                if refused:
                    raise EmailPermanentFailureError(
                        "One or more recipients were rejected."
                    )
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailAuthenticationError(
                "Email provider authentication failed."
            ) from exc
        except TimeoutError as exc:
            raise EmailTimeoutError("Email provider timed out.") from exc
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                raise EmailTemporaryFailureError(
                    "Email was temporarily rejected."
                ) from exc
            raise EmailPermanentFailureError("Email was permanently rejected.") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailProviderUnavailableError(
                "Email provider is unavailable."
            ) from exc
        return EmailSendResult(
            str(message["Message-ID"]),
            {"provider": "SMTP", "accepted_count": len(request.recipients.all)},
        )

    @staticmethod
    def build_message(request: EmailSendRequest) -> EmailMessage:
        message = EmailMessage()
        message["From"] = formataddr((request.from_name, request.from_address))
        message["To"] = ", ".join(request.recipients.to)
        if request.recipients.cc:
            message["Cc"] = ", ".join(request.recipients.cc)
        if request.reply_to:
            message["Reply-To"] = request.reply_to
        message["Subject"] = request.subject
        message["Message-ID"] = make_msgid(
            domain=request.from_address.split("@", 1)[-1]
        )
        message.set_content(request.text_body)
        message.add_alternative(request.html_body, subtype="html")
        message.add_attachment(
            request.attachment.content,
            maintype="application",
            subtype="pdf",
            filename=request.attachment.file_name,
        )
        return message
