from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.proposal_pdf import ProposalDocument, ProposalDocumentStatus
from leadpilot.application.proposal_portal import (
    PortalAccessLimitReachedError,
    PortalDownloadDisabledError,
    PortalLinkExpiredError,
    PortalLinkUnavailableError,
    PortalPasswordInvalidError,
    PortalPasswordRequiredError,
    PortalRateLimiter,
    PortalRateLimitError,
    ProposalPortalAccessRequest,
    ProposalPortalAccessService,
    ProposalPortalLinkStatus,
    ProposalPortalManagementService,
    generate_portal_token,
    hash_password,
    hash_portal_token,
    verify_password,
)
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.models import ProposalDocumentModel
from leadpilot.infrastructure.database.proposal_portal_repository import (
    ProposalPortalRepository,
)


class FakeProposalService:
    def get_proposal(self, proposal_id: int):
        if proposal_id != 7:
            raise LookupError("not tenant-owned")
        return SimpleNamespace(id=7)


class FakePdfService:
    content = b"%PDF-immutable-portal-document"
    checksum = hashlib.sha256(content).hexdigest()
    document = ProposalDocument(
        11,
        7,
        None,
        ProposalDocumentStatus.READY,
        "local",
        "organizations/1/proposals/7/export.pdf",
        "Proposal-LP-42.pdf",
        len(content),
        checksum,
        "snapshot-hash",
        2,
        datetime.now(UTC),
        datetime.now(UTC),
        None,
        "application/pdf",
    )

    def get_proposal_document(self, document_id: int):
        return self.document if document_id == 11 else None

    def download_proposal_document(self, document_id: int):
        assert document_id == 11
        return self.document, self.content


@pytest.fixture
def portal_services():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    source = {
        "branding": {
            "brand_name": "Tenant Brand",
            "primary_color": "#123456",
            "contact_email": "contact@tenant.example",
            "proposal_footer": "Tenant confidential",
        },
        "proposal": {
            "number": "LP-42",
            "title": "Operations Proposal",
            "valid_until": "2026-09-01",
            "currency": "USD",
        },
        "company": {"name": "Example Client", "industry": "Healthcare"},
        "sections": [
            {
                "key": "EXECUTIVE_SUMMARY",
                "title": "Summary",
                "content": "Approved content",
            }
        ],
        "items": [
            {
                "title": "Service",
                "quantity": "1.00",
                "unit_price": "100.00",
                "line_total": "100.00",
            }
        ],
        "commercial": {"currency": "USD", "total": "100.00"},
    }
    with Session(engine) as session, session.begin():
        session.add(
            ProposalDocumentModel(
                id=11,
                organization_id=1,
                proposal_id=7,
                document_type="PROPOSAL_PDF",
                status="READY",
                storage_provider="local",
                storage_key="private/key.pdf",
                file_name="Proposal-LP-42.pdf",
                mime_type="application/pdf",
                file_size_bytes=len(FakePdfService.content),
                sha256_checksum=FakePdfService.checksum,
                source_snapshot_hash="snapshot-hash",
                source_snapshot_json=json.dumps(source),
                branding_snapshot_json="{}",
                page_count=2,
            )
        )
    internal = ProposalPortalRepository(factory, 1)
    management = ProposalPortalManagementService(
        internal,
        FakeProposalService(),
        FakePdfService(),
        "token-pepper",
        5,
        lambda: None,
    )
    public = ProposalPortalAccessService(
        ProposalPortalRepository(factory, None),
        lambda _organization_id: FakePdfService(),
        "token-pepper",
        "metadata-pepper",
        PortalRateLimiter(20, 300),
        True,
        3,
        15,
    )
    return management, public, internal, factory


def test_token_is_high_entropy_url_safe_and_only_hash_is_persisted(
    portal_services,
) -> None:
    management, _public, internal, _factory = portal_services
    created = management.create_portal_link(7, 11)
    assert len(created.raw_token) >= 43
    assert all(
        character.isalnum() or character in "-_" for character in created.raw_token
    )
    stored = internal.get_by_id(created.link.id)
    assert stored is not None
    assert stored.token_hash == hash_portal_token(created.raw_token, "token-pepper")
    assert created.raw_token not in stored.token_hash
    assert stored.token_prefix == created.raw_token[:8]


def test_password_hash_is_salted_one_way_and_validated() -> None:
    first, second = (
        hash_password("correct horse battery"),
        hash_password("correct horse battery"),
    )
    assert first != second
    assert "correct horse battery" not in first
    assert verify_password("correct horse battery", first)
    assert not verify_password("wrong password", first)
    with pytest.raises(ValueError, match="10 to 256"):
        hash_password("short")


def test_password_prompt_and_failure_do_not_increment_access(portal_services) -> None:
    management, public, internal, _factory = portal_services
    created = management.create_portal_link(7, 11, password="correct password")
    management.activate_portal_link(created.link.id)
    with pytest.raises(PortalPasswordRequiredError):
        public.resolve_portal_access(ProposalPortalAccessRequest(created.raw_token))
    with pytest.raises(PortalPasswordInvalidError):
        public.resolve_portal_access(
            ProposalPortalAccessRequest(created.raw_token, "wrong password")
        )
    assert internal.get_by_id(created.link.id).access_count == 0  # type: ignore[union-attr]
    context = public.resolve_portal_access(
        ProposalPortalAccessRequest(created.raw_token, "correct password")
    )
    assert context.link.access_count == 1


def test_public_snapshot_excludes_internal_data_and_respects_pricing(
    portal_services,
) -> None:
    management, public, _internal, _factory = portal_services
    created = management.create_portal_link(7, 11, show_pricing=False)
    management.activate_portal_link(created.link.id)
    context = public.resolve_portal_access(
        ProposalPortalAccessRequest(created.raw_token)
    )
    view = public.get_public_proposal_view(context)
    assert view.branding["brand_name"] == "Tenant Brand"
    assert view.proposal["number"] == "LP-42"
    assert view.company["name"] == "Example Client"
    assert view.sections[0]["content"] == "Approved content"
    assert view.commercial is None
    assert "unit_price" not in view.items[0]
    assert "internal_notes" not in json.dumps(view.proposal)
    assert "private/key.pdf" not in json.dumps(view.proposal)


def test_access_limit_is_atomic_and_download_does_not_increment_views(
    portal_services,
) -> None:
    management, public, _internal, _factory = portal_services
    created = management.create_portal_link(7, 11, max_access_count=1)
    management.activate_portal_link(created.link.id)
    context = public.resolve_portal_access(
        ProposalPortalAccessRequest(created.raw_token)
    )
    filename, content = public.download_public_proposal_pdf(context)
    assert filename == "Proposal-LP-42.pdf"
    assert content == FakePdfService.content
    with pytest.raises(PortalAccessLimitReachedError):
        public.resolve_portal_access(ProposalPortalAccessRequest(created.raw_token))


def test_download_toggle_and_exact_document_are_enforced(portal_services) -> None:
    management, public, _internal, _factory = portal_services
    created = management.create_portal_link(7, 11, allow_pdf_download=False)
    management.activate_portal_link(created.link.id)
    context = public.resolve_portal_access(
        ProposalPortalAccessRequest(created.raw_token)
    )
    with pytest.raises(PortalDownloadDisabledError):
        public.download_public_proposal_pdf(context)


def test_revoked_expired_and_regenerated_links_remain_historical(
    portal_services,
) -> None:
    management, public, internal, _factory = portal_services
    revoked = management.create_portal_link(7, 11)
    management.activate_portal_link(revoked.link.id)
    management.revoke_portal_link(revoked.link.id)
    with pytest.raises(PortalLinkUnavailableError):
        public.resolve_portal_access(ProposalPortalAccessRequest(revoked.raw_token))

    expired = management.create_portal_link(
        7, 11, expires_at=datetime.now(UTC) + timedelta(milliseconds=1)
    )
    management.activate_portal_link(expired.link.id)
    with pytest.raises(PortalLinkExpiredError):
        public.resolve_portal_access(ProposalPortalAccessRequest(expired.raw_token))

    active = management.create_portal_link(7, 11)
    management.activate_portal_link(active.link.id)
    replacement = management.regenerate_portal_link(active.link.id)
    assert replacement.link.id != active.link.id
    assert (
        internal.get_by_id(active.link.id).status == ProposalPortalLinkStatus.SUPERSEDED
    )  # type: ignore[union-attr]
    with pytest.raises(PortalLinkUnavailableError):
        public.resolve_portal_access(ProposalPortalAccessRequest(active.raw_token))


def test_access_history_hashes_metadata_and_never_stores_secrets(
    portal_services,
) -> None:
    management, public, internal, _factory = portal_services
    created = management.create_portal_link(7, 11, password="correct password")
    management.activate_portal_link(created.link.id)
    context = public.resolve_portal_access(
        ProposalPortalAccessRequest(
            created.raw_token,
            "correct password",
            "203.0.113.5",
            "Example Browser/1.0",
            "session-value",
        )
    )
    events = internal.list_events(context.link.id)
    serialized = json.dumps([event.safe_metadata for event in events])
    assert events and all(event.ip_hash != "203.0.113.5" for event in events)
    assert all(event.user_agent_hash != "Example Browser/1.0" for event in events)
    assert created.raw_token not in serialized
    assert "correct password" not in serialized


def test_rate_limiter_is_deterministic_and_window_resets() -> None:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    clock = [now]
    limiter = PortalRateLimiter(2, 60, lambda: clock[0])
    limiter.check("fingerprint", "token")
    limiter.check("fingerprint", "token")
    with pytest.raises(PortalRateLimitError):
        limiter.check("fingerprint", "token")
    clock[0] += timedelta(seconds=61)
    limiter.check("fingerprint", "token")


def test_internal_repository_lookup_is_tenant_bound(portal_services) -> None:
    management, _public, _internal, factory = portal_services
    created = management.create_portal_link(7, 11)
    assert ProposalPortalRepository(factory, 2).get_by_id(created.link.id) is None


def test_generate_token_values_are_distinct() -> None:
    assert generate_portal_token() != generate_portal_token()
