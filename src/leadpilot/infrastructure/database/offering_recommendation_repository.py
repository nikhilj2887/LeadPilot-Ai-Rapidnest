from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from leadpilot.application.offering_recommendations import (
    OfferingRecommendation,
    RecommendationPriority,
    RecommendationStatus,
)
from leadpilot.infrastructure.database.models import ProposalRecommendationModel


class OfferingRecommendationRepository:
    """Tenant-bound recommendation persistence."""

    def __init__(self, factory: Callable[[], Session], organization_id: int) -> None:
        self._factory, self.organization_id = factory, organization_id

    def create_many(
        self,
        proposal_id: int,
        company_id: int,
        ai_run_id: int,
        rows: list[dict[str, Any]],
    ) -> tuple[OfferingRecommendation, ...]:
        with self._factory() as session, session.begin():
            models = []
            for row in rows:
                duplicate = session.scalar(
                    select(ProposalRecommendationModel.id).where(
                        ProposalRecommendationModel.organization_id
                        == self.organization_id,
                        ProposalRecommendationModel.proposal_id == proposal_id,
                        ProposalRecommendationModel.service_catalog_id
                        == row["service_catalog_id"],
                        ProposalRecommendationModel.status.in_(
                            (
                                RecommendationStatus.PENDING_REVIEW.value,
                                RecommendationStatus.APPROVED.value,
                                RecommendationStatus.ADDED_TO_PROPOSAL.value,
                            )
                        ),
                    )
                )
                if duplicate is not None:
                    continue
                model = ProposalRecommendationModel(
                    organization_id=self.organization_id,
                    proposal_id=proposal_id,
                    company_id=company_id,
                    ai_run_id=ai_run_id,
                    service_catalog_id=row["service_catalog_id"],
                    status=RecommendationStatus.PENDING_REVIEW.value,
                    match_score=row["match_score"],
                    deterministic_score=row["deterministic_score"],
                    priority=row["priority"],
                    recommendation_reason=row["recommendation_reason"],
                    matched_findings_json=json.dumps(row["matched_findings"]),
                    expected_benefits_json=json.dumps(row["expected_benefits"]),
                    suggested_scope=row["suggested_scope"],
                    suggested_timeline=row.get("suggested_timeline"),
                    warnings_json=json.dumps(row["warnings"]),
                )
                session.add(model)
                models.append(model)
            session.flush()
            return tuple(self._item(model) for model in models)

    def get_by_id(self, recommendation_id: int) -> OfferingRecommendation | None:
        with self._factory() as session:
            model = session.scalar(
                select(ProposalRecommendationModel).where(
                    ProposalRecommendationModel.id == recommendation_id,
                    ProposalRecommendationModel.organization_id == self.organization_id,
                )
            )
            return self._item(model) if model else None

    def list_by_proposal(self, proposal_id: int) -> tuple[OfferingRecommendation, ...]:
        with self._factory() as session:
            return tuple(
                self._item(model)
                for model in session.scalars(
                    select(ProposalRecommendationModel)
                    .where(
                        ProposalRecommendationModel.proposal_id == proposal_id,
                        ProposalRecommendationModel.organization_id
                        == self.organization_id,
                    )
                    .order_by(ProposalRecommendationModel.created_at.desc())
                )
            )

    def update_status(
        self,
        recommendation_id: int,
        expected: RecommendationStatus,
        status: RecommendationStatus,
        user_id: int | None,
    ) -> OfferingRecommendation | None:
        with self._factory() as session, session.begin():
            model = session.scalar(
                select(ProposalRecommendationModel).where(
                    ProposalRecommendationModel.id == recommendation_id,
                    ProposalRecommendationModel.organization_id == self.organization_id,
                    ProposalRecommendationModel.status == expected.value,
                )
            )
            if model is None:
                return None
            model.status, model.reviewed_by_user_id, model.reviewed_at = (
                status.value,
                user_id,
                datetime.now(UTC),
            )
            session.flush()
            session.refresh(model)
            return self._item(model)

    def mark_added(
        self, recommendation_id: int, item_id: int, user_id: int | None
    ) -> OfferingRecommendation | None:
        with self._factory() as session, session.begin():
            model = session.scalar(
                select(ProposalRecommendationModel).where(
                    ProposalRecommendationModel.id == recommendation_id,
                    ProposalRecommendationModel.organization_id == self.organization_id,
                    ProposalRecommendationModel.status
                    == RecommendationStatus.APPROVED.value,
                )
            )
            if model is None:
                return None
            model.status, model.added_proposal_item_id = (
                RecommendationStatus.ADDED_TO_PROPOSAL.value,
                item_id,
            )
            model.reviewed_by_user_id, model.reviewed_at = user_id, datetime.now(UTC)
            session.flush()
            session.refresh(model)
            return self._item(model)

    def supersede_pending(self, proposal_id: int) -> int:
        with self._factory() as session, session.begin():
            models = list(
                session.scalars(
                    select(ProposalRecommendationModel).where(
                        ProposalRecommendationModel.proposal_id == proposal_id,
                        ProposalRecommendationModel.organization_id
                        == self.organization_id,
                        ProposalRecommendationModel.status
                        == RecommendationStatus.PENDING_REVIEW.value,
                    )
                )
            )
            for model in models:
                model.status = RecommendationStatus.SUPERSEDED.value
            return len(models)

    @staticmethod
    def _item(model: ProposalRecommendationModel) -> OfferingRecommendation:
        return OfferingRecommendation(
            model.id,
            model.proposal_id,
            model.company_id,
            model.service_catalog_id,
            model.ai_run_id,
            RecommendationStatus(model.status),
            model.match_score,
            model.deterministic_score or 0,
            RecommendationPriority(model.priority),
            model.recommendation_reason,
            tuple(json.loads(model.matched_findings_json)),
            tuple(json.loads(model.expected_benefits_json)),
            model.suggested_scope,
            model.suggested_timeline,
            tuple(json.loads(model.warnings_json)),
            model.added_proposal_item_id,
            model.created_at,
        )
