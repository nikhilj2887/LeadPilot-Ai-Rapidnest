from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from leadpilot.application.proposal_pdf import (
    ProposalDocument,
    ProposalDocumentStatus,
    ProposalDocumentType,
    ProposalPdfValidationResult,
)
from leadpilot.infrastructure.database.models import ProposalDocumentModel


class ProposalDocumentRepository:
    def __init__(self, factory: Callable[[], Session], organization_id: int) -> None:
        self._factory, self.organization_id = factory, organization_id

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
    ) -> ProposalDocument:
        with self._factory() as session, session.begin():
            model = ProposalDocumentModel(
                organization_id=self.organization_id,
                proposal_id=proposal_id,
                document_type=ProposalDocumentType.PROPOSAL_PDF.value,
                status=ProposalDocumentStatus.PENDING.value,
                storage_provider=storage_provider,
                storage_key=storage_key,
                file_name=file_name,
                mime_type="application/pdf",
                source_snapshot_hash=source_hash,
                source_snapshot_json=source_json,
                branding_snapshot_json=branding_json,
                generated_by_user_id=user_id,
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._document(model)

    def mark_generating(self, document_id: int) -> None:
        self._status(
            document_id,
            ProposalDocumentStatus.PENDING,
            ProposalDocumentStatus.GENERATING,
        )

    def mark_ready(
        self, document_id: int, validation: ProposalPdfValidationResult
    ) -> ProposalDocument:
        with self._factory() as session, session.begin():
            model = self._get(session, document_id)
            if model is None or model.status != ProposalDocumentStatus.GENERATING.value:
                raise ValueError("Document is not generating.")
            (
                model.status,
                model.file_size_bytes,
                model.sha256_checksum,
                model.page_count,
                model.completed_at,
            ) = (
                ProposalDocumentStatus.READY.value,
                validation.file_size,
                validation.checksum,
                validation.page_count,
                datetime.now(UTC),
            )
            session.flush()
            session.refresh(model)
            return self._document(model)

    def mark_failed(self, document_id: int, code: str, message: str) -> None:
        with self._factory() as session, session.begin():
            model = self._get(session, document_id)
            if model:
                (
                    model.status,
                    model.error_code,
                    model.safe_error_message,
                    model.failed_at,
                ) = (
                    ProposalDocumentStatus.FAILED.value,
                    code,
                    message[:500],
                    datetime.now(UTC),
                )

    def get_by_id(self, document_id: int) -> ProposalDocument | None:
        with self._factory() as session:
            model = self._get(session, document_id)
            return self._document(model) if model else None

    def list_by_proposal(self, proposal_id: int) -> tuple[ProposalDocument, ...]:
        with self._factory() as session:
            return tuple(
                self._document(model)
                for model in session.scalars(
                    select(ProposalDocumentModel)
                    .where(
                        ProposalDocumentModel.organization_id == self.organization_id,
                        ProposalDocumentModel.proposal_id == proposal_id,
                    )
                    .order_by(
                        ProposalDocumentModel.created_at.desc(),
                        ProposalDocumentModel.id.desc(),
                    )
                )
            )

    def mark_superseded(self, document_id: int) -> ProposalDocument | None:
        with self._factory() as session, session.begin():
            model = self._get(session, document_id)
            if model is None or model.status != ProposalDocumentStatus.READY.value:
                return None
            model.status, model.superseded_at = (
                ProposalDocumentStatus.SUPERSEDED.value,
                datetime.now(UTC),
            )
            session.flush()
            session.refresh(model)
            return self._document(model)

    def _status(
        self,
        document_id: int,
        expected: ProposalDocumentStatus,
        status: ProposalDocumentStatus,
    ) -> None:
        with self._factory() as session, session.begin():
            model = self._get(session, document_id)
            if model is None or model.status != expected.value:
                raise ValueError("Invalid document transition.")
            model.status = status.value

    def _get(self, session: Session, document_id: int) -> ProposalDocumentModel | None:
        return session.scalar(
            select(ProposalDocumentModel).where(
                ProposalDocumentModel.id == document_id,
                ProposalDocumentModel.organization_id == self.organization_id,
            )
        )

    @staticmethod
    def _document(model: ProposalDocumentModel) -> ProposalDocument:
        return ProposalDocument(
            model.id,
            model.proposal_id,
            model.proposal_version_id,
            ProposalDocumentStatus(model.status),
            model.storage_provider,
            model.storage_key,
            model.file_name,
            model.file_size_bytes,
            model.sha256_checksum,
            model.source_snapshot_hash,
            model.page_count,
            model.created_at,
            model.completed_at,
            model.safe_error_message,
            model.mime_type,
        )
