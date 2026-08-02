from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pypdf import PdfReader

from leadpilot.application.proposal_pdf_snapshot import (
    ProposalPdfSnapshot,
    ProposalPdfSnapshotBuilder,
    canonical_json,
    snapshot_hash,
)


class ProposalDocumentType(StrEnum):
    PROPOSAL_PDF = "PROPOSAL_PDF"


class ProposalDocumentStatus(StrEnum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    DELETED = "DELETED"


class ProposalPdfError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProposalDocument:
    id: int
    proposal_id: int
    proposal_version_id: int | None
    status: ProposalDocumentStatus
    storage_provider: str
    storage_key: str
    file_name: str
    file_size_bytes: int | None
    sha256_checksum: str | None
    source_snapshot_hash: str
    page_count: int | None
    created_at: datetime
    completed_at: datetime | None
    safe_error_message: str | None
    mime_type: str = "application/pdf"


@dataclass(frozen=True, slots=True)
class ProposalPdfValidationResult:
    page_count: int
    file_size: int
    checksum: str


class ProposalPdfRenderer(Protocol):
    def render(self, snapshot: ProposalPdfSnapshot, *, confidential: bool) -> bytes: ...


class ProposalDocumentRepository(Protocol):
    def create_pending(
        self,
        proposal_id: int,
        file_name: str,
        storage_provider: str,
        storage_key: str,
        source_hash: str,
        source_json: str,
        branding_json: str,
        user_id: int | None,
    ) -> ProposalDocument: ...
    def mark_generating(self, document_id: int) -> None: ...
    def mark_ready(
        self, document_id: int, validation: ProposalPdfValidationResult
    ) -> ProposalDocument: ...
    def mark_failed(self, document_id: int, code: str, message: str) -> None: ...
    def get_by_id(self, document_id: int) -> ProposalDocument | None: ...
    def list_by_proposal(self, proposal_id: int) -> tuple[ProposalDocument, ...]: ...
    def mark_superseded(self, document_id: int) -> ProposalDocument | None: ...


def safe_pdf_filename(value: str | None, proposal_number: str) -> str:
    raw = value or f"Proposal-{proposal_number}.pdf"
    raw = re.sub(r"[\\/\x00-\x1f:*?\"<>|]+", "-", raw).strip(" .-")[:190]
    if not raw.lower().endswith(".pdf"):
        raw += ".pdf"
    return raw or "Proposal.pdf"


def validate_pdf(
    content: bytes, *, max_size: int, expected_text: str
) -> ProposalPdfValidationResult:
    if not content.startswith(b"%PDF-") or not content or len(content) > max_size:
        raise ProposalPdfError("Generated PDF failed size or header validation.")
    try:
        reader = PdfReader(__import__("io").BytesIO(content))
    except Exception as exc:
        raise ProposalPdfError("Generated PDF could not be parsed.") from exc
    if reader.is_encrypted or not reader.pages:
        raise ProposalPdfError("Generated PDF is encrypted or empty.")
    root = reader.trailer.get("/Root", {})
    if "/Names" in root and any(
        name in str(root["/Names"]) for name in ("/JavaScript", "/EmbeddedFiles")
    ):
        raise ProposalPdfError("Generated PDF contains prohibited active content.")
    extracted = " ".join(page.extract_text() or "" for page in reader.pages)
    if expected_text not in extracted:
        raise ProposalPdfError("Generated PDF is missing proposal identity text.")
    return ProposalPdfValidationResult(
        len(reader.pages), len(content), hashlib.sha256(content).hexdigest()
    )


class ProposalPdfService:
    def __init__(
        self,
        repository: ProposalDocumentRepository,
        builder: ProposalPdfSnapshotBuilder,
        renderer: ProposalPdfRenderer,
        storage: object,
        organization_id: int,
        user_id: int | None = None,
        authorize: object = None,
        audit: object = None,
        max_file_size_mb: int = 15,
    ) -> None:
        self._repository, self._builder, self._renderer, self._storage = (
            repository,
            builder,
            renderer,
            storage,
        )
        self._organization_id, self._user_id, self._authorize, self._audit = (
            organization_id,
            user_id,
            authorize,
            audit,
        )
        self._max_bytes = max_file_size_mb * 1024 * 1024

    def generate_proposal_pdf(
        self,
        proposal_id: int,
        *,
        file_name: str | None = None,
        include_confidential_label: bool = True,
    ) -> ProposalDocument:
        if self._authorize:
            self._authorize()
        snapshot = self._builder.build(proposal_id)
        source_hash = snapshot_hash(snapshot)
        key = f"organizations/{self._organization_id}/proposals/{proposal_id}/exports/{uuid.uuid4()}.pdf"
        document = self._repository.create_pending(
            proposal_id,
            safe_pdf_filename(file_name, snapshot.proposal["number"]),
            self._storage.provider_name,
            key,
            source_hash,
            canonical_json(snapshot),
            canonical_json(snapshot.branding),
            self._user_id,
        )
        self._repository.mark_generating(document.id)
        try:
            content = self._renderer.render(
                snapshot, confidential=include_confidential_label
            )
            validation = validate_pdf(
                content,
                max_size=self._max_bytes,
                expected_text=snapshot.proposal["number"],
            )
            self._storage.save(key, content)
            ready = self._repository.mark_ready(document.id, validation)
        except Exception as exc:
            if self._storage.exists(key):
                self._storage.delete(key)
            self._repository.mark_failed(
                document.id, type(exc).__name__, str(exc)[:500]
            )
            if self._audit:
                self._audit(
                    "PROPOSAL_PDF_GENERATION_FAILED",
                    "proposal_document",
                    str(document.id),
                )
            raise ProposalPdfError("Proposal PDF generation failed safely.") from exc
        if self._audit:
            self._audit(
                "PROPOSAL_PDF_GENERATION_COMPLETED",
                "proposal_document",
                str(document.id),
            )
        return ready

    def list_proposal_documents(self, proposal_id: int) -> tuple[ProposalDocument, ...]:
        self._builder.build(proposal_id)
        return self._repository.list_by_proposal(proposal_id)

    def get_proposal_document(self, document_id: int) -> ProposalDocument | None:
        """Return a tenant-scoped document without exposing repository details."""
        return self._repository.get_by_id(document_id)

    def download_proposal_document(
        self, document_id: int
    ) -> tuple[ProposalDocument, bytes]:
        document = self._repository.get_by_id(document_id)
        if document is None or document.status != ProposalDocumentStatus.READY:
            raise ProposalPdfError("Only ready proposal PDFs can be downloaded.")
        content = self._storage.read(document.storage_key)
        if hashlib.sha256(content).hexdigest() != document.sha256_checksum:
            raise ProposalPdfError("Stored PDF checksum validation failed.")
        if self._audit:
            self._audit(
                "PROPOSAL_PDF_DOWNLOADED", "proposal_document", str(document.id)
            )
        return document, content

    def supersede_proposal_document(self, document_id: int) -> ProposalDocument:
        if self._authorize:
            self._authorize()
        changed = self._repository.mark_superseded(document_id)
        if changed is None:
            raise ProposalPdfError("Only ready documents can be superseded.")
        return changed
