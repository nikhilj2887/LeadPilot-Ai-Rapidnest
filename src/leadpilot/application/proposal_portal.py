from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from leadpilot.application.proposal_pdf import (
    ProposalDocumentStatus,
    ProposalPdfService,
)


class ProposalPortalLinkStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    SUPERSEDED = "SUPERSEDED"


class ProposalPortalEventType(StrEnum):
    LINK_OPENED = "LINK_OPENED"
    PASSWORD_PROMPTED = "PASSWORD_PROMPTED"
    PASSWORD_SUCCEEDED = "PASSWORD_SUCCEEDED"
    PASSWORD_FAILED = "PASSWORD_FAILED"
    PROPOSAL_VIEWED = "PROPOSAL_VIEWED"
    PDF_DOWNLOAD_STARTED = "PDF_DOWNLOAD_STARTED"
    PDF_DOWNLOAD_COMPLETED = "PDF_DOWNLOAD_COMPLETED"
    PDF_DOWNLOAD_FAILED = "PDF_DOWNLOAD_FAILED"
    ACCESS_DENIED = "ACCESS_DENIED"
    LINK_EXPIRED = "LINK_EXPIRED"
    LINK_REVOKED = "LINK_REVOKED"
    ACCESS_LIMIT_REACHED = "ACCESS_LIMIT_REACHED"


class PortalAccessResult(StrEnum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILED = "FAILED"


class ProposalPortalError(ValueError):
    pass


class PortalConfigurationError(ProposalPortalError):
    pass


class PortalTokenInvalidError(ProposalPortalError):
    pass


class PortalLinkUnavailableError(ProposalPortalError):
    pass


class PortalLinkExpiredError(PortalLinkUnavailableError):
    pass


class PortalPasswordRequiredError(PortalLinkUnavailableError):
    pass


class PortalPasswordInvalidError(PortalLinkUnavailableError):
    pass


class PortalPasswordLockedError(PortalLinkUnavailableError):
    pass


class PortalAccessLimitReachedError(PortalLinkUnavailableError):
    pass


class PortalDownloadDisabledError(PortalLinkUnavailableError):
    pass


class PortalDocumentUnavailableError(PortalLinkUnavailableError):
    pass


class PortalRateLimitError(PortalLinkUnavailableError):
    pass


class PortalStateTransitionError(ProposalPortalError):
    pass


@dataclass(frozen=True, slots=True)
class ProposalPortalLink:
    id: int
    organization_id: int
    proposal_id: int
    proposal_document_id: int
    status: ProposalPortalLinkStatus
    token_hash: str
    token_prefix: str
    password_hash: str | None
    password_required: bool
    expires_at: datetime | None
    max_access_count: int | None
    access_count: int
    allow_pdf_download: bool
    show_pricing: bool
    created_by_user_id: int | None
    revoked_by_user_id: int | None
    created_at: datetime
    activated_at: datetime | None
    revoked_at: datetime | None
    last_accessed_at: datetime | None
    superseded_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProposalPortalCreation:
    link: ProposalPortalLink
    raw_token: str


@dataclass(frozen=True, slots=True)
class ProposalPortalAccessRequest:
    token: str
    password: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    session_identifier: str | None = None


@dataclass(frozen=True, slots=True)
class ProposalPortalAccessContext:
    link: ProposalPortalLink
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class ProposalPortalPublicView:
    branding: dict[str, object]
    proposal: dict[str, object]
    company: dict[str, object]
    sections: tuple[dict[str, object], ...]
    items: tuple[dict[str, object], ...]
    commercial: dict[str, object] | None
    allow_pdf_download: bool
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProposalPortalAccessEvent:
    id: int
    portal_link_id: int
    event_type: ProposalPortalEventType
    access_result: PortalAccessResult
    ip_hash: str | None
    user_agent_hash: str | None
    session_hash: str | None
    safe_metadata: dict[str, object]
    created_at: datetime


class ProposalPortalRepository(Protocol):
    def create_draft(self, values: dict[str, object]) -> ProposalPortalLink: ...
    def get_by_id(self, link_id: int) -> ProposalPortalLink | None: ...
    def get_by_token_hash(self, token_hash: str) -> ProposalPortalLink | None: ...
    def list_by_proposal(self, proposal_id: int) -> tuple[ProposalPortalLink, ...]: ...
    def transition(
        self,
        link_id: int,
        expected: ProposalPortalLinkStatus,
        status: ProposalPortalLinkStatus,
        user_id: int | None = None,
    ) -> ProposalPortalLink: ...
    def increment_access_count(self, link_id: int) -> ProposalPortalLink | None: ...
    def document_snapshot(
        self, link: ProposalPortalLink
    ) -> tuple[str, str, int, str, str] | None: ...
    def create_event(
        self,
        link: ProposalPortalLink,
        event_type: ProposalPortalEventType,
        result: PortalAccessResult,
        metadata: dict[str, str | None],
        safe_metadata: dict[str, object] | None = None,
    ) -> None: ...
    def list_events(self, link_id: int) -> tuple[ProposalPortalAccessEvent, ...]: ...


def generate_portal_token() -> str:
    return secrets.token_urlsafe(32)


def hash_portal_token(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    if not 10 <= len(password) <= 256:
        raise ProposalPortalError("Portal passwords must contain 10 to 256 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return (
        "scrypt$16384$8$1$"
        + base64.urlsafe_b64encode(salt).decode()
        + "$"
        + base64.urlsafe_b64encode(digest).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = stored.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.urlsafe_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(actual, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


class PortalRateLimiter:
    def __init__(
        self,
        attempts: int,
        window_seconds: int,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._attempts, self._window = attempts, timedelta(seconds=window_seconds)
        self._now = now or (lambda: datetime.now(UTC))
        self._events: dict[tuple[str, str], list[datetime]] = defaultdict(list)

    def check(
        self,
        fingerprint: str,
        action: str,
        *,
        limit: int | None = None,
        record: bool = True,
    ) -> None:
        now = self._now()
        key = (fingerprint, action)
        self._events[key] = [
            item for item in self._events[key] if now - item < self._window
        ]
        if len(self._events[key]) >= (limit or self._attempts):
            raise PortalRateLimitError("Proposal access is temporarily unavailable.")
        if record:
            self._events[key].append(now)


class ProposalPortalManagementService:
    def __init__(
        self,
        repository: ProposalPortalRepository,
        proposal_service: object,
        pdf_service: ProposalPdfService,
        token_pepper: str,
        user_id: int | None,
        authorize_write: object = None,
        audit: object = None,
    ) -> None:
        self._repository, self._proposals, self._pdf = (
            repository,
            proposal_service,
            pdf_service,
        )
        self._pepper, self._user_id, self._authorize, self._audit = (
            token_pepper,
            user_id,
            authorize_write,
            audit,
        )

    def create_portal_link(
        self,
        proposal_id: int,
        proposal_document_id: int,
        *,
        expires_at: datetime | None = None,
        password: str | None = None,
        max_access_count: int | None = None,
        allow_pdf_download: bool = True,
        show_pricing: bool = True,
    ) -> ProposalPortalCreation:
        self._authorize_action()
        self._proposals.get_proposal(proposal_id)
        document = self._pdf.get_proposal_document(proposal_document_id)
        if (
            not document
            or document.proposal_id != proposal_id
            or document.status != ProposalDocumentStatus.READY
        ):
            raise PortalDocumentUnavailableError("A READY proposal PDF is required.")
        now = datetime.now(UTC)
        if expires_at and self._aware(expires_at) <= now:
            raise ProposalPortalError("Portal expiry must be in the future.")
        if max_access_count is not None and max_access_count <= 0:
            raise ProposalPortalError("Maximum access count must be positive.")
        raw_token = generate_portal_token()
        link = self._repository.create_draft(
            {
                "proposal_id": proposal_id,
                "proposal_document_id": proposal_document_id,
                "status": ProposalPortalLinkStatus.DRAFT,
                "token_hash": hash_portal_token(raw_token, self._pepper),
                "token_prefix": raw_token[:8],
                "password_hash": hash_password(password) if password else None,
                "password_required": bool(password),
                "expires_at": self._aware(expires_at) if expires_at else None,
                "max_access_count": max_access_count,
                "access_count": 0,
                "allow_pdf_download": allow_pdf_download,
                "show_pricing": show_pricing,
                "show_internal_branding_details": False,
                "created_by_user_id": self._user_id,
            }
        )
        self._event("PROPOSAL_PORTAL_LINK_CREATED", link.id)
        return ProposalPortalCreation(link, raw_token)

    def activate_portal_link(self, link_id: int) -> ProposalPortalLink:
        self._authorize_action()
        link = self._repository.transition(
            link_id, ProposalPortalLinkStatus.DRAFT, ProposalPortalLinkStatus.ACTIVE
        )
        self._event("PROPOSAL_PORTAL_LINK_ACTIVATED", link.id)
        return link

    def revoke_portal_link(self, link_id: int) -> ProposalPortalLink:
        self._authorize_action()
        link = self.get_portal_link(link_id)
        if link.status not in {
            ProposalPortalLinkStatus.DRAFT,
            ProposalPortalLinkStatus.ACTIVE,
        }:
            raise PortalStateTransitionError(
                "Link cannot be revoked from its current state."
            )
        changed = self._repository.transition(
            link.id, link.status, ProposalPortalLinkStatus.REVOKED, self._user_id
        )
        self._event("PROPOSAL_PORTAL_LINK_REVOKED", changed.id)
        return changed

    def supersede_portal_link(self, link_id: int) -> ProposalPortalLink:
        self._authorize_action()
        link = self.get_portal_link(link_id)
        if link.status not in {
            ProposalPortalLinkStatus.ACTIVE,
            ProposalPortalLinkStatus.EXPIRED,
        }:
            raise PortalStateTransitionError(
                "Link cannot be superseded from its current state."
            )
        changed = self._repository.transition(
            link.id, link.status, ProposalPortalLinkStatus.SUPERSEDED
        )
        self._event("PROPOSAL_PORTAL_LINK_SUPERSEDED", changed.id)
        return changed

    def regenerate_portal_link(
        self, link_id: int, **overrides: object
    ) -> ProposalPortalCreation:
        old = self.get_portal_link(link_id)
        created = self.create_portal_link(
            old.proposal_id,
            old.proposal_document_id,
            expires_at=overrides.get("expires_at", old.expires_at),
            password=overrides.get("password"),
            max_access_count=overrides.get("max_access_count", old.max_access_count),
            allow_pdf_download=bool(
                overrides.get("allow_pdf_download", old.allow_pdf_download)
            ),
            show_pricing=bool(overrides.get("show_pricing", old.show_pricing)),
        )
        if old.status in {
            ProposalPortalLinkStatus.ACTIVE,
            ProposalPortalLinkStatus.EXPIRED,
        }:
            self.supersede_portal_link(old.id)
        self._event("PROPOSAL_PORTAL_LINK_REGENERATED", created.link.id)
        return created

    def get_portal_link(self, link_id: int) -> ProposalPortalLink:
        link = self._repository.get_by_id(link_id)
        if not link:
            raise PortalLinkUnavailableError("Portal link was not found.")
        return link

    def list_portal_links(self, proposal_id: int) -> tuple[ProposalPortalLink, ...]:
        self._proposals.get_proposal(proposal_id)
        return self._repository.list_by_proposal(proposal_id)

    def get_access_history(self, link_id: int) -> tuple[ProposalPortalAccessEvent, ...]:
        self.get_portal_link(link_id)
        return self._repository.list_events(link_id)

    def get_portal_metrics(self, proposal_id: int) -> dict[str, int]:
        links = self.list_portal_links(proposal_id)
        return {
            "total": len(links),
            "active": sum(
                link.status == ProposalPortalLinkStatus.ACTIVE for link in links
            ),
            "accesses": sum(link.access_count for link in links),
        }

    def _authorize_action(self) -> None:
        if self._authorize:
            self._authorize()

    def _event(self, action: str, link_id: int) -> None:
        if self._audit:
            self._audit(action, "proposal_portal_link", str(link_id))

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )


class ProposalPortalAccessService:
    def __init__(
        self,
        repository: ProposalPortalRepository,
        pdf_service_factory: Callable[[int], ProposalPdfService],
        token_pepper: str,
        metadata_pepper: str,
        rate_limiter: PortalRateLimiter,
        record_events: bool = True,
        password_max_attempts: int = 5,
        max_attachment_mb: int = 15,
    ) -> None:
        self._repository, self._pdf_factory = repository, pdf_service_factory
        self._pepper, self._metadata_pepper, self._limiter = (
            token_pepper,
            metadata_pepper,
            rate_limiter,
        )
        self._record_events, self._password_attempts = (
            record_events,
            password_max_attempts,
        )
        self._max_bytes = max_attachment_mb * 1024 * 1024

    def resolve_portal_access(
        self, request: ProposalPortalAccessRequest
    ) -> ProposalPortalAccessContext:
        fingerprint = self._fingerprint(
            request.ip_address or request.session_identifier or "anonymous"
        )
        self._limiter.check(fingerprint, "token", record=False)
        if not 32 <= len(request.token) <= 128 or not all(
            char.isalnum() or char in "-_" for char in request.token
        ):
            self._limiter.check(fingerprint, "token")
            raise PortalTokenInvalidError("Proposal unavailable.")
        link = self._repository.get_by_token_hash(
            hash_portal_token(request.token, self._pepper)
        )
        if not link:
            self._limiter.check(fingerprint, "token")
            raise PortalLinkUnavailableError("Proposal unavailable.")
        metadata = self._metadata(request)
        self._record(
            link,
            ProposalPortalEventType.LINK_OPENED,
            PortalAccessResult.SUCCESS,
            metadata,
        )
        now = datetime.now(UTC)
        if link.status == ProposalPortalLinkStatus.REVOKED:
            self._record(
                link,
                ProposalPortalEventType.LINK_REVOKED,
                PortalAccessResult.DENIED,
                metadata,
            )
            raise PortalLinkUnavailableError("Proposal unavailable.")
        if link.status != ProposalPortalLinkStatus.ACTIVE:
            raise PortalLinkUnavailableError("Proposal unavailable.")
        if link.expires_at and self._aware(link.expires_at) <= now:
            self._repository.transition(
                link.id,
                ProposalPortalLinkStatus.ACTIVE,
                ProposalPortalLinkStatus.EXPIRED,
            )
            self._record(
                link,
                ProposalPortalEventType.LINK_EXPIRED,
                PortalAccessResult.DENIED,
                metadata,
            )
            raise PortalLinkExpiredError("This proposal link has expired.")
        if (
            link.max_access_count is not None
            and link.access_count >= link.max_access_count
        ):
            self._record(
                link,
                ProposalPortalEventType.ACCESS_LIMIT_REACHED,
                PortalAccessResult.DENIED,
                metadata,
            )
            raise PortalAccessLimitReachedError("Proposal unavailable.")
        if link.password_required:
            if request.password is None:
                self._record(
                    link,
                    ProposalPortalEventType.PASSWORD_PROMPTED,
                    PortalAccessResult.SUCCESS,
                    metadata,
                )
                raise PortalPasswordRequiredError("Password required.")
            self._limiter.check(
                fingerprint,
                f"password:{link.id}",
                limit=self._password_attempts,
                record=False,
            )
            if not link.password_hash or not verify_password(
                request.password, link.password_hash
            ):
                self._limiter.check(
                    fingerprint,
                    f"password:{link.id}",
                    limit=self._password_attempts,
                )
                self._record(
                    link,
                    ProposalPortalEventType.PASSWORD_FAILED,
                    PortalAccessResult.DENIED,
                    metadata,
                )
                raise PortalPasswordInvalidError("Proposal unavailable.")
            self._record(
                link,
                ProposalPortalEventType.PASSWORD_SUCCEEDED,
                PortalAccessResult.SUCCESS,
                metadata,
            )
        changed = self._repository.increment_access_count(link.id)
        if not changed:
            raise PortalAccessLimitReachedError("Proposal unavailable.")
        self._record(
            changed,
            ProposalPortalEventType.PROPOSAL_VIEWED,
            PortalAccessResult.SUCCESS,
            metadata,
        )
        return ProposalPortalAccessContext(changed, fingerprint)

    def context_matches_token(
        self, context: ProposalPortalAccessContext, token: str
    ) -> bool:
        if not token:
            return False
        return hmac.compare_digest(
            context.link.token_hash, hash_portal_token(token, self._pepper)
        )

    def get_public_proposal_view(
        self, context: ProposalPortalAccessContext
    ) -> ProposalPortalPublicView:
        stored = self._repository.document_snapshot(context.link)
        if not stored:
            raise PortalDocumentUnavailableError("Proposal document is unavailable.")
        source_json, _key, _size, _checksum, mime = stored
        if mime != "application/pdf":
            raise PortalDocumentUnavailableError("Proposal document is unavailable.")
        snapshot = json.loads(source_json)
        items = tuple(snapshot.get("items", ()))
        if not context.link.show_pricing:
            items = tuple(
                {
                    key: item.get(key)
                    for key in ("title", "description", "timeline")
                    if item.get(key) is not None
                }
                for item in items
            )
        return ProposalPortalPublicView(
            branding={
                key: snapshot.get("branding", {}).get(key)
                for key in (
                    "brand_name",
                    "primary_color",
                    "secondary_color",
                    "accent_color",
                    "website",
                    "contact_email",
                    "contact_phone",
                    "proposal_footer",
                )
            },
            proposal={
                key: snapshot.get("proposal", {}).get(key)
                for key in ("number", "title", "issue_date", "valid_until", "currency")
            },
            company={
                key: snapshot.get("company", {}).get(key)
                for key in ("name", "industry", "website", "country", "city")
            },
            sections=tuple(snapshot.get("sections", ())),
            items=items,
            commercial=snapshot.get("commercial")
            if context.link.show_pricing
            else None,
            allow_pdf_download=context.link.allow_pdf_download,
            expires_at=context.link.expires_at,
        )

    def download_public_proposal_pdf(
        self, context: ProposalPortalAccessContext
    ) -> tuple[str, bytes]:
        link = context.link
        if not link.allow_pdf_download:
            raise PortalDownloadDisabledError("PDF download is unavailable.")
        self._limiter.check(context.request_fingerprint, f"download:{link.id}")
        self._record(
            link,
            ProposalPortalEventType.PDF_DOWNLOAD_STARTED,
            PortalAccessResult.SUCCESS,
            {},
        )
        document = self._pdf_factory(link.organization_id).get_proposal_document(
            link.proposal_document_id
        )
        if (
            not document
            or document.proposal_id != link.proposal_id
            or document.status != ProposalDocumentStatus.READY
            or document.mime_type != "application/pdf"
        ):
            self._record(
                link,
                ProposalPortalEventType.PDF_DOWNLOAD_FAILED,
                PortalAccessResult.FAILED,
                {},
            )
            raise PortalDocumentUnavailableError("PDF download is unavailable.")
        try:
            document, content = self._pdf_factory(
                link.organization_id
            ).download_proposal_document(document.id)
        except Exception as exc:
            self._record(
                link,
                ProposalPortalEventType.PDF_DOWNLOAD_FAILED,
                PortalAccessResult.FAILED,
                {},
            )
            raise PortalDocumentUnavailableError(
                "PDF download is unavailable."
            ) from exc
        if len(content) > self._max_bytes:
            raise PortalDocumentUnavailableError("PDF download is unavailable.")
        self._record(
            link,
            ProposalPortalEventType.PDF_DOWNLOAD_COMPLETED,
            PortalAccessResult.SUCCESS,
            {},
        )
        return document.file_name, content

    def _metadata(self, request: ProposalPortalAccessRequest) -> dict[str, str | None]:
        return {
            "ip_hash": self._fingerprint(request.ip_address)
            if request.ip_address
            else None,
            "user_agent_hash": self._fingerprint(request.user_agent)
            if request.user_agent
            else None,
            "session_hash": self._fingerprint(request.session_identifier)
            if request.session_identifier
            else None,
        }

    def _fingerprint(self, value: str | None) -> str:
        return hmac.new(
            self._metadata_pepper.encode(), (value or "").encode(), hashlib.sha256
        ).hexdigest()

    def _record(
        self,
        link: ProposalPortalLink,
        event: ProposalPortalEventType,
        result: PortalAccessResult,
        metadata: dict[str, str | None],
    ) -> None:
        if self._record_events:
            self._repository.create_event(link, event, result, metadata)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )
