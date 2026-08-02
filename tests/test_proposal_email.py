from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from leadpilot.application.proposal_email import (
    EmailAttachment,
    EmailAttachmentError,
    EmailAuthenticationError,
    EmailHeaderInjectionError,
    EmailPermanentFailureError,
    EmailProviderConfiguration,
    EmailProviderName,
    EmailRecipientValidationError,
    EmailSendRequest,
    EmailTemporaryFailureError,
    EmailTimeoutError,
    ProposalEmailDeliveryStatus,
    ProposalEmailService,
    ProposalEmailTemplateBuilder,
    delivery_idempotency_key,
    normalize_recipients,
)
from leadpilot.application.proposal_pdf import ProposalDocument, ProposalDocumentStatus
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.proposal_email_repository import (
    ProposalEmailRepository,
)
from leadpilot.infrastructure.email_providers import (
    FakeEmailProvider,
    SMTPEmailProvider,
)


def request() -> EmailSendRequest:
    recipients = normalize_recipients(
        "client@example.com", "copy@example.com", "secret@example.com"
    )
    attachment = EmailAttachment(
        "Proposal-LP-42.pdf", "application/pdf", b"%PDF-test", "abc"
    )
    return EmailSendRequest(
        "sender@tenant.example",
        "Tenant Sales",
        "reply@tenant.example",
        recipients,
        "Proposal LP-42",
        "<p>Safe preview</p>",
        "Safe preview",
        attachment,
        delivery_idempotency_key(
            "abc", recipients, "Proposal LP-42", "<p>Safe preview</p>"
        ),
    )


def test_recipients_are_normalized_deduplicated_and_precedence_applies() -> None:
    result = normalize_recipients(
        "CLIENT@example.com, second@example.com",
        "client@example.com, copy@example.com",
        "copy@example.com, hidden@example.com, client@example.com",
    )
    assert result.to == ("client@example.com", "second@example.com")
    assert result.cc == ("copy@example.com",)
    assert result.bcc == ("hidden@example.com",)
    assert normalize_recipients("client@example.com", "", "").cc == ()


@pytest.mark.parametrize(
    "value", ["", "not-an-email", "a@example.com\nBcc:x@example.com"]
)
def test_recipient_validation_rejects_missing_malformed_and_injected(
    value: str,
) -> None:
    error = (
        EmailHeaderInjectionError if "\n" in value else EmailRecipientValidationError
    )
    with pytest.raises(error):
        normalize_recipients(value)


def test_recipient_limits_are_bounded() -> None:
    with pytest.raises(EmailRecipientValidationError, match="limit"):
        normalize_recipients([f"user{i}@example.com" for i in range(11)])


def test_template_is_tenant_branded_escaped_and_has_plain_text() -> None:
    subject, html_body, text_body = ProposalEmailTemplateBuilder().build(
        tenant_name="Acme & Partners",
        primary_color="#123456",
        proposal_number="LP-42",
        proposal_title="Operations <script>alert(1)</script>",
        client_name="Client <img src=x>",
        valid_until=date(2026, 9, 1),
        sender_name="Acme Sales",
        sender_address="sales@acme.example",
        footer="Acme confidential",
        intro="Hello <b>team</b>",
    )
    assert subject == "Proposal LP-42 – Operations <script>alert(1)</script>"
    assert "Acme &amp; Partners" in html_body
    assert "&lt;script&gt;" in html_body and "<script>" not in html_body
    assert "#123456" in html_body
    assert "2026-09-01" in text_body
    assert "RapidNest" not in html_body + text_body


def test_template_rejects_header_injection_and_long_body() -> None:
    builder = ProposalEmailTemplateBuilder()
    kwargs = {
        "tenant_name": "Tenant",
        "primary_color": "#000000",
        "proposal_number": "LP-1",
        "proposal_title": "Title",
        "client_name": "Client",
        "valid_until": None,
        "sender_name": "Sender",
        "sender_address": "sender@example.com",
        "footer": None,
    }
    with pytest.raises(EmailHeaderInjectionError):
        builder.build(**kwargs, subject="Safe\nBcc: hidden@example.com")
    with pytest.raises(ValueError, match="5,000"):
        builder.build(**kwargs, intro="x" * 5001)


@pytest.mark.parametrize(
    ("mode", "error"),
    [
        ("authentication_failure", EmailAuthenticationError),
        ("timeout", EmailTimeoutError),
        ("temporary_failure", EmailTemporaryFailureError),
        ("permanent_rejection", EmailPermanentFailureError),
        ("attachment_rejection", EmailAttachmentError),
    ],
)
def test_fake_provider_has_deterministic_safe_failure_modes(
    mode: str, error: type[Exception]
) -> None:
    provider = FakeEmailProvider(mode)
    with pytest.raises(error):
        provider.send(request())
    assert provider.requests == [request()]


def test_fake_provider_success_is_deterministic_and_captures_request() -> None:
    provider = FakeEmailProvider()
    first = provider.send(request())
    second = provider.send(request())
    assert first.provider_message_id == second.provider_message_id
    assert first.safe_metadata == {"accepted_count": 3, "provider": "FAKE"}
    assert len(provider.requests) == 2


def test_smtp_message_has_alternatives_pdf_and_never_exposes_bcc_header() -> None:
    message = SMTPEmailProvider.build_message(request())
    assert message["From"] == "Tenant Sales <sender@tenant.example>"
    assert message["To"] == "client@example.com"
    assert message["Cc"] == "copy@example.com"
    assert message["Bcc"] is None
    assert message["Reply-To"] == "reply@tenant.example"
    parts = list(message.walk())
    assert any(part.get_content_type() == "text/plain" for part in parts)
    assert any(part.get_content_type() == "text/html" for part in parts)
    pdf = next(part for part in parts if part.get_content_type() == "application/pdf")
    assert pdf.get_filename() == "Proposal-LP-42.pdf"


def test_smtp_configuration_contains_transport_controls_without_persisting_secret() -> (
    None
):
    configuration = EmailProviderConfiguration(
        provider=EmailProviderName.SMTP,
        from_address="sender@example.com",
        from_name="Sender",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_password="runtime-secret",
        use_tls=False,
        use_ssl=True,
    )
    assert configuration.smtp_password == "runtime-secret"
    assert configuration.use_ssl and not configuration.use_tls


class FakeProposalService:
    def get_proposal(self, proposal_id: int):
        if proposal_id != 7:
            raise LookupError("not tenant-owned")
        return SimpleNamespace(
            id=7,
            proposal_number="LP-42",
            title="Operations",
            company_name="Client Co",
            valid_until=date(2026, 9, 1),
        )


class FakePdfService:
    content = b"%PDF-safe-immutable"
    checksum = hashlib.sha256(content).hexdigest()
    document = ProposalDocument(
        11,
        7,
        None,
        ProposalDocumentStatus.READY,
        "local",
        "hidden/storage/key.pdf",
        "Proposal-LP-42.pdf",
        len(content),
        checksum,
        "source-hash",
        2,
        datetime.now(UTC),
        datetime.now(UTC),
        None,
    )

    def get_proposal_document(self, document_id: int):
        return self.document if document_id == self.document.id else None

    def download_proposal_document(self, document_id: int):
        assert document_id == self.document.id
        return self.document, self.content


@pytest.fixture
def email_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    provider = FakeEmailProvider()
    service = ProposalEmailService(
        ProposalEmailRepository(factory, 1),
        FakeProposalService(),
        FakePdfService(),
        provider,
        EmailProviderConfiguration(
            EmailProviderName.FAKE,
            "sender@tenant.example",
            "Tenant Sales",
            "reply@tenant.example",
            max_retries=2,
        ),
        ProposalEmailTemplateBuilder(),
        SimpleNamespace(display_name="Tenant One"),
        SimpleNamespace(
            brand_name="Tenant Brand",
            primary_color="#123456",
            email_signature="Tenant footer",
        ),
        5,
        lambda: None,
        None,
        15,
    )
    return service, provider, factory


def test_delivery_lifecycle_idempotency_and_immutable_resend(email_service) -> None:
    service, provider, _factory = email_service
    draft = service.create_email_draft(
        7, 11, to_addresses="client@example.com", bcc_addresses="hidden@example.com"
    )
    duplicate = service.create_email_draft(
        7, 11, to_addresses="CLIENT@example.com", bcc_addresses="hidden@example.com"
    )
    assert duplicate.id == draft.id
    preview = service.preview_email_delivery(draft.id)
    assert preview.masked_bcc == ("***@example.com",)
    sent = service.send_email_delivery(draft.id)
    assert sent.status == ProposalEmailDeliveryStatus.SENT
    assert sent.attempt_count == 1
    assert provider.requests[0].attachment.content == FakePdfService.content
    assert service.send_email_delivery(draft.id).id == sent.id
    resend = service.resend_proposal_email(sent.id)
    assert resend.id != sent.id
    assert resend.original_delivery_id == sent.id
    assert (
        service.get_email_delivery(sent.id).status == ProposalEmailDeliveryStatus.SENT
    )


def test_transient_failure_can_retry_but_permanent_failure_cannot(
    email_service,
) -> None:
    service, provider, _factory = email_service
    draft = service.create_email_draft(7, 11, to_addresses="client@example.com")
    provider.mode = "timeout"
    failed = service.send_email_delivery(draft.id)
    assert failed.status == ProposalEmailDeliveryStatus.FAILED
    assert failed.safe_error_code == "EmailTimeoutError"
    provider.mode = "success"
    assert (
        service.retry_email_delivery(failed.id).status
        == ProposalEmailDeliveryStatus.SENT
    )

    permanent = service.create_email_draft(7, 11, to_addresses="other@example.com")
    provider.mode = "permanent_rejection"
    permanent = service.send_email_delivery(permanent.id)
    with pytest.raises(ValueError, match="transient"):
        service.retry_email_delivery(permanent.id)


def test_repository_get_is_tenant_bound(email_service) -> None:
    service, _provider, factory = email_service
    draft = service.create_email_draft(7, 11, to_addresses="client@example.com")
    assert ProposalEmailRepository(factory, 2).get_by_id(draft.id) is None
