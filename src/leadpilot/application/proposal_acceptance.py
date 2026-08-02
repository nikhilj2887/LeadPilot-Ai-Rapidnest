from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from PIL import Image, ImageChops
from reportlab.lib.utils import ImageReader

from leadpilot.application.proposal_portal import ProposalPortalAccessContext

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ProposalAcceptanceStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class SignatureType(StrEnum):
    TYPED = "TYPED"
    HANDWRITTEN = "HANDWRITTEN"


class ProposalAcceptanceError(ValueError):
    pass


class AcceptanceValidationError(ProposalAcceptanceError):
    pass


class AcceptanceAlreadyCompletedError(ProposalAcceptanceError):
    pass


class AcceptanceUnavailableError(ProposalAcceptanceError):
    pass


@dataclass(frozen=True, slots=True)
class ProposalAcceptance:
    id: int
    organization_id: int
    proposal_id: int
    portal_link_id: int
    proposal_document_id: int
    signed_document_id: int | None
    status: ProposalAcceptanceStatus
    accepted_by_name: str | None
    accepted_by_email: str | None
    accepted_by_company: str | None
    accepted_by_title: str | None
    signature_type: SignatureType | None
    typed_signature: str | None
    signature_image_path: str | None
    comments: str | None
    evidence_hash: str | None
    accepted_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AcceptanceSubmission:
    legal_name: str
    email: str
    company: str
    title: str | None
    comments: str | None
    signature_type: SignatureType
    typed_signature: str | None = None
    signature_png: bytes | str | None = None
    authorized: bool = False


@dataclass(frozen=True, slots=True)
class AcceptanceEvidence:
    proposal_number: str
    proposal_title: str
    tenant_name: str
    tenant_primary_color: str
    client_name: str
    accepted_by_name: str
    accepted_by_email: str
    accepted_by_company: str
    accepted_by_title: str | None
    signature_type: SignatureType
    typed_signature: str | None
    signature_png: bytes | None
    comments: str | None
    accepted_at: datetime
    original_document_checksum: str
    evidence_hash: str


class AcceptanceRepository(Protocol):
    def accepted_for_proposal(
        self, organization_id: int, proposal_id: int
    ) -> ProposalAcceptance | None: ...
    def acceptance_for_link(self, link_id: int) -> ProposalAcceptance | None: ...
    def accept(
        self,
        context: ProposalPortalAccessContext,
        values: dict[str, object],
        signed_document: dict[str, object],
    ) -> ProposalAcceptance: ...
    def reject(
        self,
        context: ProposalPortalAccessContext,
        comments: str | None,
        metadata: dict[str, str | None],
        rejected_at: datetime,
    ) -> ProposalAcceptance: ...
    def list_by_proposal(self, proposal_id: int) -> tuple[ProposalAcceptance, ...]: ...


class SignedAcceptanceRenderer(Protocol):
    def render(self, original_pdf: bytes, evidence: AcceptanceEvidence) -> bytes: ...


def validate_signature_png(value: bytes | str | None) -> bytes:
    if isinstance(value, str):
        prefix = "data:image/png;base64,"
        if not value.startswith(prefix):
            raise AcceptanceValidationError(
                "Handwritten signature must be a PNG image."
            )
        try:
            content = base64.b64decode(value[len(prefix) :], validate=True)
        except ValueError as exc:
            raise AcceptanceValidationError(
                "Handwritten signature is invalid."
            ) from exc
    elif isinstance(value, bytes):
        content = value
    else:
        raise AcceptanceValidationError("A handwritten signature is required.")
    if (
        not content.startswith(b"\x89PNG\r\n\x1a\n")
        or not 100 <= len(content) <= 2_000_000
    ):
        raise AcceptanceValidationError(
            "Handwritten signature must be a non-empty PNG image."
        )
    try:
        width, height = ImageReader(io.BytesIO(content)).getSize()
        image = Image.open(io.BytesIO(content)).convert("RGB")
        background = Image.new("RGB", image.size, image.getpixel((0, 0)))
        if ImageChops.difference(image, background).getbbox() is None:
            raise AcceptanceValidationError(
                "Handwritten signature must contain a visible signature."
            )
    except AcceptanceValidationError:
        raise
    except Exception as exc:
        raise AcceptanceValidationError(
            "Handwritten signature PNG could not be read."
        ) from exc
    if width < 40 or height < 20:
        raise AcceptanceValidationError("Handwritten signature is too small.")
    return content


class ProposalAcceptanceService:
    def __init__(
        self,
        repository: AcceptanceRepository,
        portal_repository: object,
        pdf_service_factory: object,
        storage: object,
        renderer: SignedAcceptanceRenderer,
        metadata_pepper: str,
        audit: object = None,
    ) -> None:
        self._repository, self._portal_repository = repository, portal_repository
        self._pdf_factory, self._storage, self._renderer = (
            pdf_service_factory,
            storage,
            renderer,
        )
        self._pepper, self._audit = metadata_pepper, audit

    def accept_proposal(
        self,
        context: ProposalPortalAccessContext,
        submission: AcceptanceSubmission,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        session_identifier: str | None = None,
    ) -> ProposalAcceptance:
        link = context.link
        if self._repository.accepted_for_proposal(
            link.organization_id, link.proposal_id
        ):
            raise AcceptanceAlreadyCompletedError(
                "This proposal has already been accepted."
            )
        values, signature_png = self._validate_submission(submission)
        document, original_pdf = self._pdf_factory(
            link.organization_id
        ).download_proposal_document(link.proposal_document_id)
        stored = self._portal_repository.document_snapshot(link)
        if not stored or document.sha256_checksum != stored[3]:
            raise AcceptanceUnavailableError("Proposal acceptance is unavailable.")
        snapshot = json.loads(stored[0])
        accepted_at = datetime.now(UTC)
        signature_checksum = hashlib.sha256(
            signature_png or (submission.typed_signature or "").encode()
        ).hexdigest()
        evidence_payload = json.dumps(
            {
                "organization": link.organization_id,
                "proposal": link.proposal_id,
                "portal_link": link.id,
                "document_checksum": document.sha256_checksum,
                "accepted_by": values,
                "signature_checksum": signature_checksum,
                "accepted_at": accepted_at.isoformat(),
            },
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        evidence_hash = hashlib.sha256(evidence_payload.encode()).hexdigest()
        branding = snapshot.get("branding", {})
        proposal = snapshot.get("proposal", {})
        company = snapshot.get("company", {})
        evidence = AcceptanceEvidence(
            str(proposal.get("number", "Proposal")),
            str(proposal.get("title", "Proposal")),
            str(branding.get("brand_name", "Proposal")),
            str(branding.get("primary_color", "#2563EB")),
            str(company.get("name", "Client")),
            values["accepted_by_name"],
            values["accepted_by_email"],
            values["accepted_by_company"],
            values["accepted_by_title"],
            submission.signature_type,
            values["typed_signature"],
            signature_png,
            values["comments"],
            accepted_at,
            document.sha256_checksum or "",
            evidence_hash,
        )
        signed_pdf = self._renderer.render(original_pdf, evidence)
        if not signed_pdf.startswith(b"%PDF-"):
            raise AcceptanceUnavailableError("Signed copy generation failed safely.")
        base_key = f"organizations/{link.organization_id}/proposals/{link.proposal_id}/acceptances/{uuid.uuid4()}"
        signature_key = f"{base_key}/signature.png" if signature_png else None
        pdf_key = f"{base_key}/signed-copy.pdf"
        if signature_key:
            self._storage.save(signature_key, signature_png)
        self._storage.save(pdf_key, signed_pdf)
        try:
            acceptance = self._repository.accept(
                context,
                {
                    **values,
                    "signature_image_path": signature_key,
                    "evidence_hash": evidence_hash,
                    "accepted_at": accepted_at,
                    **self._metadata(ip_address, user_agent, session_identifier),
                },
                {
                    "storage_provider": self._storage.provider_name,
                    "storage_key": pdf_key,
                    "file_name": f"Signed-{document.file_name}",
                    "file_size_bytes": len(signed_pdf),
                    "sha256_checksum": hashlib.sha256(signed_pdf).hexdigest(),
                    "source_snapshot_hash": evidence_hash,
                    "source_snapshot_json": evidence_payload,
                    "branding_snapshot_json": json.dumps(branding, sort_keys=True),
                    "page_count": self._page_count(signed_pdf),
                },
            )
        except Exception:
            self._storage.delete(pdf_key)
            if signature_key:
                self._storage.delete(signature_key)
            raise
        self._event("SIGNATURE_CAPTURED", acceptance.id)
        self._event("SIGNED_COPY_GENERATED", acceptance.id)
        self._event("PROPOSAL_ACCEPTED", acceptance.id)
        return acceptance

    def reject_proposal(
        self,
        context: ProposalPortalAccessContext,
        reason: str | None = None,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        session_identifier: str | None = None,
    ) -> ProposalAcceptance:
        if self._repository.accepted_for_proposal(
            context.link.organization_id, context.link.proposal_id
        ):
            raise AcceptanceAlreadyCompletedError(
                "This proposal has already been accepted."
            )
        reason = reason.strip()[:5000] if reason and reason.strip() else None
        result = self._repository.reject(
            context,
            reason,
            self._metadata(ip_address, user_agent, session_identifier),
            datetime.now(UTC),
        )
        self._event("PROPOSAL_REJECTED", result.id)
        return result

    def get_for_portal(
        self, context: ProposalPortalAccessContext
    ) -> ProposalAcceptance | None:
        return self._repository.acceptance_for_link(context.link.id)

    def list_acceptances(self, proposal_id: int) -> tuple[ProposalAcceptance, ...]:
        return self._repository.list_by_proposal(proposal_id)

    def download_signed_copy(self, acceptance: ProposalAcceptance) -> tuple[str, bytes]:
        if (
            acceptance.status != ProposalAcceptanceStatus.ACCEPTED
            or acceptance.signed_document_id is None
        ):
            raise AcceptanceUnavailableError("Signed copy is unavailable.")
        document, content = self._pdf_factory(
            acceptance.organization_id
        ).download_proposal_document(acceptance.signed_document_id)
        return document.file_name, content

    def read_signature(self, acceptance: ProposalAcceptance) -> bytes | None:
        if not acceptance.signature_image_path:
            return None
        return self._storage.read(acceptance.signature_image_path)

    def _validate_submission(
        self, submission: AcceptanceSubmission
    ) -> tuple[dict[str, object], bytes | None]:
        if not submission.authorized:
            raise AcceptanceValidationError("Authorization confirmation is required.")
        name = submission.legal_name.strip()
        email = submission.email.strip().lower()
        company = submission.company.strip()
        title = (
            submission.title.strip()[:200]
            if submission.title and submission.title.strip()
            else None
        )
        comments = (
            submission.comments.strip()[:5000]
            if submission.comments and submission.comments.strip()
            else None
        )
        if (
            not 2 <= len(name) <= 200
            or not 1 <= len(company) <= 200
            or not EMAIL_PATTERN.fullmatch(email)
        ):
            raise AcceptanceValidationError(
                "Valid signer name, email, and company are required."
            )
        signature_png = None
        typed = None
        if submission.signature_type == SignatureType.TYPED:
            typed = (submission.typed_signature or "").strip()
            if typed != name:
                raise AcceptanceValidationError(
                    "Typed signature must match the legal name."
                )
        else:
            signature_png = validate_signature_png(submission.signature_png)
        return {
            "accepted_by_name": name,
            "accepted_by_email": email,
            "accepted_by_company": company,
            "accepted_by_title": title,
            "comments": comments,
            "signature_type": submission.signature_type,
            "typed_signature": typed,
        }, signature_png

    def _metadata(
        self, ip: str | None, agent: str | None, session: str | None
    ) -> dict[str, str | None]:
        return {
            "client_ip_hash": self._hash(ip),
            "client_user_agent_hash": self._hash(agent),
            "client_session_hash": self._hash(session),
        }

    def _hash(self, value: str | None) -> str | None:
        return (
            hashlib.sha256(f"{self._pepper}:{value}".encode()).hexdigest()
            if value
            else None
        )

    def _event(self, action: str, acceptance_id: int) -> None:
        if self._audit:
            self._audit(action, "proposal_acceptance", str(acceptance_id))

    @staticmethod
    def _page_count(content: bytes) -> int:
        from io import BytesIO

        from pypdf import PdfReader

        return len(PdfReader(BytesIO(content)).pages)
