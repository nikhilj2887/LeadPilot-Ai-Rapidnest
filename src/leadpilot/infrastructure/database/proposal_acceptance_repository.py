from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadpilot.application.proposal_acceptance import (
    AcceptanceAlreadyCompletedError,
    AcceptanceUnavailableError,
    ProposalAcceptance,
    ProposalAcceptanceStatus,
    SignatureType,
)
from leadpilot.application.proposal_portal import (
    ProposalPortalAccessContext,
    ProposalPortalLinkStatus,
)
from leadpilot.infrastructure.database.models import (
    ProposalAcceptanceModel,
    ProposalActivityModel,
    ProposalDocumentModel,
    ProposalModel,
    ProposalPortalLinkModel,
)


class ProposalAcceptanceRepository:
    def __init__(
        self, factory: Callable[[], Session], organization_id: int | None
    ) -> None:
        self._factory, self.organization_id = factory, organization_id

    def accepted_for_proposal(
        self, organization_id: int, proposal_id: int
    ) -> ProposalAcceptance | None:
        if self.organization_id is not None and organization_id != self.organization_id:
            return None
        with self._factory() as session:
            model = session.scalar(
                select(ProposalAcceptanceModel).where(
                    ProposalAcceptanceModel.organization_id == organization_id,
                    ProposalAcceptanceModel.proposal_id == proposal_id,
                    ProposalAcceptanceModel.status
                    == ProposalAcceptanceStatus.ACCEPTED.value,
                )
            )
            return self._acceptance(model) if model else None

    def acceptance_for_link(self, link_id: int) -> ProposalAcceptance | None:
        with self._factory() as session:
            statement = (
                select(ProposalAcceptanceModel)
                .where(ProposalAcceptanceModel.proposal_portal_link_id == link_id)
                .order_by(
                    ProposalAcceptanceModel.created_at.desc(),
                    ProposalAcceptanceModel.id.desc(),
                )
            )
            if self.organization_id is not None:
                statement = statement.where(
                    ProposalAcceptanceModel.organization_id == self.organization_id
                )
            model = session.scalar(statement)
            return self._acceptance(model) if model else None

    def accept(
        self,
        context: ProposalPortalAccessContext,
        values: dict[str, object],
        signed_document: dict[str, object],
    ) -> ProposalAcceptance:
        link = context.link
        self._require_tenant(link.organization_id)
        try:
            with self._factory() as session, session.begin():
                self._validate_link(session, context)
                completed = session.scalar(
                    select(ProposalAcceptanceModel.id).where(
                        ProposalAcceptanceModel.organization_id == link.organization_id,
                        ProposalAcceptanceModel.proposal_portal_link_id == link.id,
                        ProposalAcceptanceModel.status.in_(
                            (
                                ProposalAcceptanceStatus.ACCEPTED.value,
                                ProposalAcceptanceStatus.REJECTED.value,
                            )
                        ),
                    )
                )
                if completed is not None:
                    raise AcceptanceAlreadyCompletedError(
                        "A response has already been recorded."
                    )
                if self._accepted_model(
                    session, link.organization_id, link.proposal_id
                ):
                    raise AcceptanceAlreadyCompletedError(
                        "This proposal has already been accepted."
                    )
                proposal = session.scalar(
                    select(ProposalModel).where(
                        ProposalModel.id == link.proposal_id,
                        ProposalModel.organization_id == link.organization_id,
                    )
                )
                if not proposal:
                    raise AcceptanceUnavailableError(
                        "Proposal acceptance is unavailable."
                    )
                acceptance = ProposalAcceptanceModel(
                    organization_id=link.organization_id,
                    proposal_id=link.proposal_id,
                    proposal_portal_link_id=link.id,
                    proposal_document_id=link.proposal_document_id,
                    status=ProposalAcceptanceStatus.ACCEPTED.value,
                    **values,
                )
                session.add(acceptance)
                session.flush()
                document = ProposalDocumentModel(
                    organization_id=link.organization_id,
                    proposal_id=link.proposal_id,
                    document_type="SIGNED_ACCEPTANCE_PDF",
                    status="READY",
                    mime_type="application/pdf",
                    completed_at=values["accepted_at"],
                    **signed_document,
                )
                session.add(document)
                session.flush()
                acceptance.signed_document_id = document.id
                proposal.status = "ACCEPTED"
                proposal.accepted_at = values["accepted_at"]
                activity_details = json.dumps(
                    {
                        "acceptance_id": acceptance.id,
                        "evidence_hash": acceptance.evidence_hash,
                    },
                    sort_keys=True,
                )
                session.add_all(
                    [
                        ProposalActivityModel(
                            organization_id=link.organization_id,
                            proposal_id=link.proposal_id,
                            activity_type=activity_type,
                            details_json=activity_details,
                        )
                        for activity_type in (
                            "SIGNATURE_CAPTURED",
                            "SIGNED_COPY_GENERATED",
                            "PROPOSAL_ACCEPTED",
                        )
                    ]
                )
                session.flush()
                session.refresh(acceptance)
                return self._acceptance(acceptance)
        except IntegrityError as exc:
            raise AcceptanceAlreadyCompletedError(
                "This proposal has already been accepted."
            ) from exc

    def reject(
        self,
        context: ProposalPortalAccessContext,
        comments: str | None,
        metadata: dict[str, str | None],
        rejected_at: datetime,
    ) -> ProposalAcceptance:
        link = context.link
        self._require_tenant(link.organization_id)
        with self._factory() as session, session.begin():
            self._validate_link(session, context)
            existing = session.scalar(
                select(ProposalAcceptanceModel).where(
                    ProposalAcceptanceModel.organization_id == link.organization_id,
                    ProposalAcceptanceModel.proposal_portal_link_id == link.id,
                    ProposalAcceptanceModel.status.in_(
                        (
                            ProposalAcceptanceStatus.ACCEPTED.value,
                            ProposalAcceptanceStatus.REJECTED.value,
                        )
                    ),
                )
            )
            if existing:
                raise AcceptanceAlreadyCompletedError(
                    "A response has already been recorded."
                )
            proposal = session.scalar(
                select(ProposalModel).where(
                    ProposalModel.id == link.proposal_id,
                    ProposalModel.organization_id == link.organization_id,
                )
            )
            if not proposal or proposal.status == "ACCEPTED":
                raise AcceptanceAlreadyCompletedError(
                    "This proposal has already been accepted."
                )
            model = ProposalAcceptanceModel(
                organization_id=link.organization_id,
                proposal_id=link.proposal_id,
                proposal_portal_link_id=link.id,
                proposal_document_id=link.proposal_document_id,
                status=ProposalAcceptanceStatus.REJECTED.value,
                comments=comments,
                rejected_at=rejected_at,
                **metadata,
            )
            session.add(model)
            proposal.status = "REJECTED"
            proposal.rejected_at = rejected_at
            session.flush()
            session.add(
                ProposalActivityModel(
                    organization_id=link.organization_id,
                    proposal_id=link.proposal_id,
                    activity_type="PROPOSAL_REJECTED",
                    details_json=json.dumps({"acceptance_id": model.id}),
                )
            )
            session.refresh(model)
            return self._acceptance(model)

    def list_by_proposal(self, proposal_id: int) -> tuple[ProposalAcceptance, ...]:
        if self.organization_id is None:
            return ()
        with self._factory() as session:
            return tuple(
                self._acceptance(model)
                for model in session.scalars(
                    select(ProposalAcceptanceModel)
                    .where(
                        ProposalAcceptanceModel.organization_id == self.organization_id,
                        ProposalAcceptanceModel.proposal_id == proposal_id,
                    )
                    .order_by(
                        ProposalAcceptanceModel.created_at.desc(),
                        ProposalAcceptanceModel.id.desc(),
                    )
                )
            )

    def _validate_link(
        self, session: Session, context: ProposalPortalAccessContext
    ) -> None:
        link = context.link
        model = session.scalar(
            select(ProposalPortalLinkModel).where(
                ProposalPortalLinkModel.id == link.id,
                ProposalPortalLinkModel.organization_id == link.organization_id,
                ProposalPortalLinkModel.proposal_id == link.proposal_id,
                ProposalPortalLinkModel.proposal_document_id
                == link.proposal_document_id,
                ProposalPortalLinkModel.status == ProposalPortalLinkStatus.ACTIVE.value,
            )
        )
        if not model:
            raise AcceptanceUnavailableError("Proposal acceptance is unavailable.")

    def _require_tenant(self, organization_id: int) -> None:
        if self.organization_id is not None and self.organization_id != organization_id:
            raise AcceptanceUnavailableError("Proposal acceptance is unavailable.")

    @staticmethod
    def _accepted_model(
        session: Session, organization_id: int, proposal_id: int
    ) -> ProposalAcceptanceModel | None:
        return session.scalar(
            select(ProposalAcceptanceModel).where(
                ProposalAcceptanceModel.organization_id == organization_id,
                ProposalAcceptanceModel.proposal_id == proposal_id,
                ProposalAcceptanceModel.status
                == ProposalAcceptanceStatus.ACCEPTED.value,
            )
        )

    @staticmethod
    def _acceptance(model: ProposalAcceptanceModel) -> ProposalAcceptance:
        return ProposalAcceptance(
            model.id,
            model.organization_id,
            model.proposal_id,
            model.proposal_portal_link_id,
            model.proposal_document_id,
            model.signed_document_id,
            ProposalAcceptanceStatus(model.status),
            model.accepted_by_name,
            model.accepted_by_email,
            model.accepted_by_company,
            model.accepted_by_title,
            SignatureType(model.signature_type) if model.signature_type else None,
            model.typed_signature,
            model.signature_image_path,
            model.comments,
            model.evidence_hash,
            model.accepted_at,
            model.rejected_at,
            model.created_at,
        )
