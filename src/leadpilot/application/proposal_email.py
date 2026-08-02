from __future__ import annotations

import hashlib
import html
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parseaddr
from enum import StrEnum
from typing import Protocol

from leadpilot.application.proposal_pdf import (
    ProposalDocumentStatus,
    ProposalPdfService,
)

CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)


class EmailProviderName(StrEnum):
    SMTP = "SMTP"
    MICROSOFT_GRAPH = "MICROSOFT_GRAPH"
    GMAIL = "GMAIL"
    SENDGRID = "SENDGRID"
    POSTMARK = "POSTMARK"
    SES = "SES"
    FAKE = "FAKE"


class ProposalEmailDeliveryStatus(StrEnum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class EmailError(ValueError):
    pass


class EmailConfigurationError(EmailError):
    pass


class EmailRecipientValidationError(EmailError):
    pass


class EmailHeaderInjectionError(EmailRecipientValidationError):
    pass


class EmailAttachmentError(EmailError):
    pass


class EmailAttachmentChecksumError(EmailAttachmentError):
    pass


class EmailAttachmentTooLargeError(EmailAttachmentError):
    pass


class EmailDeliveryStateError(EmailError):
    pass


class EmailProviderUnavailableError(EmailError):
    pass


class EmailAuthenticationError(EmailError):
    pass


class EmailTimeoutError(EmailError):
    pass


class EmailTemporaryFailureError(EmailError):
    pass


class EmailPermanentFailureError(EmailError):
    pass


@dataclass(frozen=True, slots=True)
class EmailRecipientSet:
    to: tuple[str, ...]
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()

    @property
    def all(self) -> tuple[str, ...]:
        return self.to + self.cc + self.bcc


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    file_name: str
    mime_type: str
    content: bytes
    checksum: str


@dataclass(frozen=True, slots=True)
class EmailSendRequest:
    from_address: str
    from_name: str
    reply_to: str | None
    recipients: EmailRecipientSet
    subject: str
    html_body: str
    text_body: str
    attachment: EmailAttachment
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class EmailSendResult:
    provider_message_id: str
    safe_metadata: dict[str, str | int]


@dataclass(frozen=True, slots=True)
class EmailProviderConfiguration:
    provider: EmailProviderName
    from_address: str
    from_name: str
    reply_to: str | None = None
    id: int | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: int = 30
    max_retries: int = 2


@dataclass(frozen=True, slots=True)
class ProposalEmailDelivery:
    id: int
    proposal_id: int
    proposal_document_id: int
    status: ProposalEmailDeliveryStatus
    provider: EmailProviderName
    from_address: str
    from_name: str
    reply_to: str | None
    recipients: EmailRecipientSet
    subject: str
    html_body: str
    text_body: str
    attachment_file_name: str
    attachment_checksum: str
    idempotency_key: str | None
    attempt_count: int
    provider_message_id: str | None
    safe_error_code: str | None
    safe_error_message: str | None
    created_at: datetime
    sent_at: datetime | None
    original_delivery_id: int | None = None


@dataclass(frozen=True, slots=True)
class ProposalEmailPreview:
    delivery: ProposalEmailDelivery
    attachment_size: int
    masked_bcc: tuple[str, ...]


class EmailProvider(Protocol):
    def send(self, request: EmailSendRequest) -> EmailSendResult: ...


class ProposalEmailRepository(Protocol):
    def create_draft(self, values: dict[str, object]) -> ProposalEmailDelivery: ...
    def get_by_id(self, delivery_id: int) -> ProposalEmailDelivery | None: ...
    def list_by_proposal(
        self, proposal_id: int
    ) -> tuple[ProposalEmailDelivery, ...]: ...
    def find_by_idempotency_key(self, key: str) -> ProposalEmailDelivery | None: ...
    def transition(
        self,
        delivery_id: int,
        expected: ProposalEmailDeliveryStatus,
        status: ProposalEmailDeliveryStatus,
        **values: object,
    ) -> ProposalEmailDelivery: ...
    def increment_attempt(self, delivery_id: int) -> ProposalEmailDelivery: ...


def normalize_recipients(
    to: list[str] | tuple[str, ...] | str,
    cc: list[str] | tuple[str, ...] | str | None = None,
    bcc: list[str] | tuple[str, ...] | str | None = None,
) -> EmailRecipientSet:
    def clean(
        values: list[str] | tuple[str, ...] | str | None, limit: int
    ) -> list[str]:
        raw = values.split(",") if isinstance(values, str) else list(values or ())
        result: list[str] = []
        for candidate in raw:
            candidate = candidate.strip()
            if not candidate:
                continue
            if CONTROL_PATTERN.search(candidate):
                raise EmailHeaderInjectionError(
                    "Recipient fields cannot contain control characters."
                )
            _, address = parseaddr(candidate)
            normalized = address.lower()
            if not EMAIL_PATTERN.fullmatch(normalized):
                raise EmailRecipientValidationError(
                    "One or more recipient addresses are invalid."
                )
            if normalized not in result:
                result.append(normalized)
        if len(result) > limit:
            raise EmailRecipientValidationError("Recipient limit exceeded.")
        return result

    to_values = clean(to, 10)
    if not to_values:
        raise EmailRecipientValidationError("At least one To recipient is required.")
    cc_values = [item for item in clean(cc, 10) if item not in to_values]
    bcc_values = [
        item
        for item in clean(bcc, 10)
        if item not in to_values and item not in cc_values
    ]
    if len(to_values) + len(cc_values) + len(bcc_values) > 25:
        raise EmailRecipientValidationError("Total recipient limit exceeded.")
    return EmailRecipientSet(tuple(to_values), tuple(cc_values), tuple(bcc_values))


def validate_header(value: str, *, maximum: int, label: str) -> str:
    value = value.strip()
    if not value or len(value) > maximum:
        raise EmailRecipientValidationError(
            f"{label} must be between 1 and {maximum} characters."
        )
    if CONTROL_PATTERN.search(value):
        raise EmailHeaderInjectionError(f"{label} cannot contain control characters.")
    return value


class ProposalEmailTemplateBuilder:
    def build(
        self,
        *,
        tenant_name: str,
        primary_color: str,
        proposal_number: str,
        proposal_title: str,
        client_name: str,
        valid_until: date | None,
        sender_name: str,
        sender_address: str,
        footer: str | None,
        intro: str | None = None,
        closing: str | None = None,
        subject: str | None = None,
    ) -> tuple[str, str, str]:
        subject_value = validate_header(
            subject or f"Proposal {proposal_number} – {proposal_title}",
            maximum=300,
            label="Subject",
        )
        intro_value = (
            intro
            or f"Please find our proposal for {client_name} attached for your review."
        ).strip()
        closing_value = (
            closing or "Please contact us if you have any questions."
        ).strip()
        if len(intro_value) > 5000 or len(closing_value) > 5000:
            raise EmailError("Email message fields must not exceed 5,000 characters.")
        color = (
            primary_color
            if re.fullmatch(r"#[0-9A-Fa-f]{6}", primary_color or "")
            else "#2563EB"
        )
        validity = (
            f"This proposal is valid until {valid_until.isoformat()}."
            if valid_until
            else ""
        )
        safe = {
            key: html.escape(str(value))
            for key, value in {
                "tenant": tenant_name,
                "number": proposal_number,
                "title": proposal_title,
                "client": client_name,
                "intro": intro_value,
                "closing": closing_value,
                "sender": sender_name,
                "address": sender_address,
                "validity": validity,
                "footer": footer or tenant_name,
            }.items()
        }
        html_body = (
            f'<div style="font-family:Arial,sans-serif;color:#111827;max-width:680px">'
            f'<div style="border-top:6px solid {color};padding:24px 0"><h2>{safe["tenant"]}</h2></div>'
            f"<p>Hello {safe['client']},</p><p>{safe['intro']}</p>"
            f"<h3>{safe['number']} — {safe['title']}</h3>"
            "<p>The complete proposal is attached as a PDF.</p>"
            f"<p>{safe['validity']}</p><p>{safe['closing']}</p>"
            f"<p>{safe['sender']}<br>{safe['address']}</p>"
            f'<footer style="border-top:1px solid #d1d5db;margin-top:24px;padding-top:12px">{safe["footer"]}</footer></div>'
        )
        text_body = "\n\n".join(
            filter(
                None,
                (
                    tenant_name,
                    f"Hello {client_name},",
                    intro_value,
                    f"{proposal_number} — {proposal_title}",
                    "The complete proposal is attached as a PDF.",
                    validity,
                    closing_value,
                    f"{sender_name}\n{sender_address}",
                    footer or tenant_name,
                ),
            )
        )
        return subject_value, html_body, text_body


def delivery_idempotency_key(
    document_checksum: str, recipients: EmailRecipientSet, subject: str, html_body: str
) -> str:
    payload = json.dumps(
        {
            "document": document_checksum,
            "to": recipients.to,
            "cc": recipients.cc,
            "bcc": recipients.bcc,
            "subject": subject,
            "body": hashlib.sha256(html_body.encode()).hexdigest(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class ProposalEmailService:
    def __init__(
        self,
        repository: ProposalEmailRepository,
        proposal_service: object,
        pdf_service: ProposalPdfService,
        provider: EmailProvider | None,
        configuration: EmailProviderConfiguration | None,
        template_builder: ProposalEmailTemplateBuilder,
        organization: object,
        branding: object | None,
        user_id: int | None,
        authorize_send: object = None,
        audit: object = None,
        max_attachment_mb: int = 15,
    ) -> None:
        self._repository, self._proposals, self._pdf, self._provider = (
            repository,
            proposal_service,
            pdf_service,
            provider,
        )
        self.configuration, self._templates, self._organization, self._branding = (
            configuration,
            template_builder,
            organization,
            branding,
        )
        self._user_id, self._authorize, self._audit = user_id, authorize_send, audit
        self._max_attachment = max_attachment_mb * 1024 * 1024

    @property
    def configured(self) -> bool:
        return self.configuration is not None and self._provider is not None

    def create_email_draft(
        self,
        proposal_id: int,
        proposal_document_id: int,
        *,
        to_addresses: list[str] | tuple[str, ...] | str,
        cc_addresses: list[str] | tuple[str, ...] | str | None = None,
        bcc_addresses: list[str] | tuple[str, ...] | str | None = None,
        subject: str | None = None,
        intro_message: str | None = None,
        closing_message: str | None = None,
        original_delivery_id: int | None = None,
    ) -> ProposalEmailDelivery:
        self._require_send()
        config = self._require_config()
        proposal = self._proposals.get_proposal(proposal_id)
        document, _content = self._attachment(proposal_id, proposal_document_id)
        recipients = normalize_recipients(to_addresses, cc_addresses, bcc_addresses)
        branding_name = (
            self._branding.brand_name
            if self._branding
            else self._organization.display_name
        )
        subject_value, html_body, text_body = self._templates.build(
            tenant_name=branding_name,
            primary_color=self._branding.primary_color if self._branding else "#2563EB",
            proposal_number=proposal.proposal_number,
            proposal_title=proposal.title,
            client_name=proposal.company_name,
            valid_until=proposal.valid_until,
            sender_name=config.from_name,
            sender_address=config.from_address,
            footer=self._branding.email_signature if self._branding else None,
            intro=intro_message,
            closing=closing_message,
            subject=subject,
        )
        key = delivery_idempotency_key(
            document.sha256_checksum or "", recipients, subject_value, html_body
        )
        if original_delivery_id is not None:
            key = hashlib.sha256(f"{key}:resend:{uuid.uuid4()}".encode()).hexdigest()
        existing = self._repository.find_by_idempotency_key(key)
        if existing and existing.status in {
            ProposalEmailDeliveryStatus.DRAFT,
            ProposalEmailDeliveryStatus.QUEUED,
            ProposalEmailDeliveryStatus.SENDING,
            ProposalEmailDeliveryStatus.SENT,
        }:
            return existing
        delivery = self._repository.create_draft(
            {
                "proposal_id": proposal_id,
                "proposal_document_id": document.id,
                "provider_config_id": config.id,
                "original_delivery_id": original_delivery_id,
                "status": ProposalEmailDeliveryStatus.DRAFT,
                "from_address": config.from_address,
                "from_name": config.from_name,
                "reply_to": config.reply_to,
                "recipients": recipients,
                "subject": subject_value,
                "html_body": html_body,
                "text_body": text_body,
                "attachment_file_name": document.file_name,
                "attachment_checksum": document.sha256_checksum,
                "provider": config.provider,
                "idempotency_key": key,
                "created_by_user_id": self._user_id,
            }
        )
        self._event("PROPOSAL_EMAIL_DRAFT_CREATED", delivery.id)
        return delivery

    def preview_email_delivery(self, delivery_id: int) -> ProposalEmailPreview:
        delivery = self.get_email_delivery(delivery_id)
        document, content = self._attachment(
            delivery.proposal_id, delivery.proposal_document_id
        )
        if document.sha256_checksum != delivery.attachment_checksum:
            raise EmailAttachmentChecksumError("Attachment identity changed.")
        return ProposalEmailPreview(
            delivery,
            len(content),
            tuple("***@" + item.split("@", 1)[1] for item in delivery.recipients.bcc),
        )

    def send_email_delivery(self, delivery_id: int) -> ProposalEmailDelivery:
        self._require_send()
        self._require_config()
        delivery = self.get_email_delivery(delivery_id)
        if delivery.status == ProposalEmailDeliveryStatus.SENT:
            return delivery
        if delivery.status not in {
            ProposalEmailDeliveryStatus.DRAFT,
            ProposalEmailDeliveryStatus.FAILED,
        }:
            raise EmailDeliveryStateError(
                "Delivery cannot be sent from its current state."
            )
        document, content = self._attachment(
            delivery.proposal_id, delivery.proposal_document_id
        )
        if document.sha256_checksum != delivery.attachment_checksum:
            raise EmailAttachmentChecksumError(
                "Attachment checksum does not match the draft."
            )
        self._repository.transition(
            delivery.id, delivery.status, ProposalEmailDeliveryStatus.QUEUED
        )
        self._repository.transition(
            delivery.id,
            ProposalEmailDeliveryStatus.QUEUED,
            ProposalEmailDeliveryStatus.SENDING,
        )
        delivery = self._repository.increment_attempt(delivery.id)
        self._event("PROPOSAL_EMAIL_SEND_STARTED", delivery.id)
        request = EmailSendRequest(
            delivery.from_address,
            delivery.from_name,
            delivery.reply_to,
            delivery.recipients,
            delivery.subject,
            delivery.html_body,
            delivery.text_body,
            EmailAttachment(
                document.file_name,
                "application/pdf",
                content,
                delivery.attachment_checksum,
            ),
            delivery.idempotency_key or "",
        )
        try:
            result = self._provider.send(request)  # type: ignore[union-attr]
        except EmailError as exc:
            failed = self._repository.transition(
                delivery.id,
                ProposalEmailDeliveryStatus.SENDING,
                ProposalEmailDeliveryStatus.FAILED,
                safe_error_code=type(exc).__name__,
                safe_error_message=str(exc)[:500],
            )
            self._event("PROPOSAL_EMAIL_FAILED", failed.id)
            return failed
        except Exception:  # noqa: BLE001 - provider boundary must fail closed
            failed = self._repository.transition(
                delivery.id,
                ProposalEmailDeliveryStatus.SENDING,
                ProposalEmailDeliveryStatus.FAILED,
                safe_error_code="EmailProviderUnavailableError",
                safe_error_message="Email provider is unavailable.",
            )
            self._event("PROPOSAL_EMAIL_FAILED", failed.id)
            return failed
        sent = self._repository.transition(
            delivery.id,
            ProposalEmailDeliveryStatus.SENDING,
            ProposalEmailDeliveryStatus.SENT,
            provider_message_id=result.provider_message_id,
            provider_response_json=json.dumps(result.safe_metadata, sort_keys=True),
        )
        self._event("PROPOSAL_EMAIL_SENT", sent.id)
        return sent

    def retry_email_delivery(self, delivery_id: int) -> ProposalEmailDelivery:
        delivery = self.get_email_delivery(delivery_id)
        if (
            delivery.status != ProposalEmailDeliveryStatus.FAILED
            or delivery.safe_error_code
            not in {
                "EmailTimeoutError",
                "EmailTemporaryFailureError",
                "EmailProviderUnavailableError",
            }
        ):
            raise EmailDeliveryStateError(
                "Only transient failed deliveries can be retried."
            )
        if delivery.attempt_count > self._require_config().max_retries:
            raise EmailDeliveryStateError("Retry limit reached.")
        self._event("PROPOSAL_EMAIL_RETRY_STARTED", delivery.id)
        return self.send_email_delivery(delivery.id)

    def resend_proposal_email(
        self,
        delivery_id: int,
        *,
        to_addresses: str | None = None,
        cc_addresses: str | None = None,
        bcc_addresses: str | None = None,
    ) -> ProposalEmailDelivery:
        original = self.get_email_delivery(delivery_id)
        if original.status != ProposalEmailDeliveryStatus.SENT:
            raise EmailDeliveryStateError("Only sent deliveries can be resent.")
        draft = self.create_email_draft(
            original.proposal_id,
            original.proposal_document_id,
            to_addresses=to_addresses or original.recipients.to,
            cc_addresses=cc_addresses
            if cc_addresses is not None
            else original.recipients.cc,
            bcc_addresses=bcc_addresses
            if bcc_addresses is not None
            else original.recipients.bcc,
            subject=original.subject,
            original_delivery_id=original.id,
        )
        self._event("PROPOSAL_EMAIL_RESENT", draft.id)
        return draft

    def cancel_email_delivery(self, delivery_id: int) -> ProposalEmailDelivery:
        self._require_send()
        delivery = self.get_email_delivery(delivery_id)
        if delivery.status not in {
            ProposalEmailDeliveryStatus.DRAFT,
            ProposalEmailDeliveryStatus.QUEUED,
        }:
            raise EmailDeliveryStateError(
                "Only draft or queued deliveries can be cancelled."
            )
        cancelled = self._repository.transition(
            delivery.id, delivery.status, ProposalEmailDeliveryStatus.CANCELLED
        )
        self._event("PROPOSAL_EMAIL_CANCELLED", delivery.id)
        return cancelled

    def get_email_delivery(self, delivery_id: int) -> ProposalEmailDelivery:
        delivery = self._repository.get_by_id(delivery_id)
        if not delivery:
            raise EmailError("Email delivery was not found.")
        return delivery

    def list_email_deliveries(
        self, proposal_id: int
    ) -> tuple[ProposalEmailDelivery, ...]:
        self._proposals.get_proposal(proposal_id)
        return self._repository.list_by_proposal(proposal_id)

    def get_email_metrics(self, proposal_id: int) -> dict[str, int]:
        records = self.list_email_deliveries(proposal_id)
        return {
            status.value: sum(record.status == status for record in records)
            for status in ProposalEmailDeliveryStatus
        }

    def _attachment(self, proposal_id: int, document_id: int):
        document = self._pdf.get_proposal_document(document_id)
        if (
            not document
            or document.proposal_id != proposal_id
            or document.status != ProposalDocumentStatus.READY
        ):
            raise EmailAttachmentError("A READY proposal PDF is required.")
        if (
            document.mime_type != "application/pdf"
            or not document.file_name.lower().endswith(".pdf")
            or CONTROL_PATTERN.search(document.file_name)
            or "/" in document.file_name
            or "\\" in document.file_name
        ):
            raise EmailAttachmentError("Proposal attachment metadata is invalid.")
        document, content = self._pdf.download_proposal_document(document_id)
        if len(content) > self._max_attachment:
            raise EmailAttachmentTooLargeError(
                "Proposal PDF exceeds the attachment limit."
            )
        return document, content

    def _require_config(self) -> EmailProviderConfiguration:
        if not self.configured:
            raise EmailConfigurationError("Email is not configured.")
        config = self.configuration
        assert config is not None
        normalize_recipients(config.from_address)
        if config.reply_to:
            normalize_recipients(config.reply_to)
        validate_header(config.from_name, maximum=200, label="Sender name")
        if config.use_tls and config.use_ssl:
            raise EmailConfigurationError("TLS and SSL cannot both be enabled.")
        if not 1 <= config.smtp_port <= 65535:
            raise EmailConfigurationError("SMTP port is invalid.")
        return config

    def _require_send(self) -> None:
        if self._authorize:
            self._authorize()

    def _event(self, action: str, delivery_id: int) -> None:
        if self._audit:
            self._audit(action, "proposal_email_delivery", str(delivery_id))
