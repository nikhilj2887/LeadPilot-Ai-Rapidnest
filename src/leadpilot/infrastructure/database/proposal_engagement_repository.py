from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from leadpilot.application.proposal_engagement import (
    EngagementEvent,
    EngagementEventType,
)
from leadpilot.application.proposal_portal import ProposalPortalAccessContext
from leadpilot.infrastructure.database.models import (
    ProposalEngagementEventModel,
    ProposalModel,
    ProposalPortalLinkModel,
)


class ProposalEngagementRepository:
    def __init__(
        self, factory: Callable[[], Session], organization_id: int | None
    ) -> None:
        self._factory, self.organization_id = factory, organization_id

    def create_event(
        self, context: ProposalPortalAccessContext, values: dict[str, object]
    ) -> EngagementEvent:
        link = context.link
        if (
            self.organization_id is not None
            and self.organization_id != link.organization_id
        ):
            raise ValueError("Proposal engagement is unavailable.")
        with self._factory() as session, session.begin():
            exists = session.scalar(
                select(ProposalPortalLinkModel.id).where(
                    ProposalPortalLinkModel.id == link.id,
                    ProposalPortalLinkModel.organization_id == link.organization_id,
                    ProposalPortalLinkModel.proposal_id == link.proposal_id,
                    ProposalPortalLinkModel.proposal_document_id
                    == link.proposal_document_id,
                )
            )
            if exists is None:
                raise ValueError("Proposal engagement is unavailable.")
            model = ProposalEngagementEventModel(
                organization_id=link.organization_id,
                proposal_id=link.proposal_id,
                portal_link_id=link.id,
                proposal_document_id=link.proposal_document_id,
                **values,
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._event(model)

    def list_by_proposal(self, proposal_id: int) -> tuple[EngagementEvent, ...]:
        if self.organization_id is None:
            return ()
        with self._factory() as session:
            statement = select(ProposalEngagementEventModel).where(
                ProposalEngagementEventModel.organization_id == self.organization_id
            )
            if proposal_id:
                statement = statement.where(
                    ProposalEngagementEventModel.proposal_id == proposal_id
                )
            return tuple(
                self._event(model)
                for model in session.scalars(
                    statement.order_by(
                        ProposalEngagementEventModel.created_at,
                        ProposalEngagementEventModel.id,
                    )
                )
            )

    def organization_status_counts(self) -> dict[str, int]:
        if self.organization_id is None:
            return {}
        with self._factory() as session:
            return {
                status: count
                for status, count in session.execute(
                    select(ProposalModel.status, func.count(ProposalModel.id))
                    .where(ProposalModel.organization_id == self.organization_id)
                    .group_by(ProposalModel.status)
                )
            }

    def proposal_count(self) -> int:
        if self.organization_id is None:
            return 0
        with self._factory() as session:
            return int(
                session.scalar(
                    select(func.count(ProposalModel.id)).where(
                        ProposalModel.organization_id == self.organization_id
                    )
                )
                or 0
            )

    def purge_before(self, cutoff: datetime) -> int:
        if self.organization_id is None:
            return 0
        with self._factory() as session, session.begin():
            result = session.execute(
                delete(ProposalEngagementEventModel).where(
                    ProposalEngagementEventModel.organization_id
                    == self.organization_id,
                    ProposalEngagementEventModel.created_at < cutoff,
                )
            )
            return int(result.rowcount or 0)

    @staticmethod
    def _event(model: ProposalEngagementEventModel) -> EngagementEvent:
        return EngagementEvent(
            model.id,
            model.organization_id,
            model.proposal_id,
            model.portal_link_id,
            model.proposal_document_id,
            model.visitor_id,
            model.session_id,
            EngagementEventType(model.event_type),
            model.page_number,
            model.section_key,
            model.duration_ms,
            json.loads(model.metadata_json or "{}"),
            model.ip_hash,
            model.user_agent_hash,
            model.created_at,
        )
