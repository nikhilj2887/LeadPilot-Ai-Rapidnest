from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from leadpilot.application.proposal_portal import (
    PortalAccessResult,
    ProposalPortalAccessEvent,
    ProposalPortalEventType,
    ProposalPortalLink,
    ProposalPortalLinkStatus,
)
from leadpilot.infrastructure.database.models import (
    ProposalDocumentModel,
    ProposalPortalAccessEventModel,
    ProposalPortalLinkModel,
)


class ProposalPortalRepository:
    def __init__(
        self, factory: Callable[[], Session], organization_id: int | None
    ) -> None:
        self._factory, self.organization_id = factory, organization_id

    def create_draft(self, values: dict[str, object]) -> ProposalPortalLink:
        if self.organization_id is None:
            raise ValueError("Tenant context is required for portal management.")
        with self._factory() as session, session.begin():
            model = ProposalPortalLinkModel(
                organization_id=self.organization_id, **values
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._link(model)

    def get_by_id(self, link_id: int) -> ProposalPortalLink | None:
        if self.organization_id is None:
            return None
        with self._factory() as session:
            model = session.scalar(
                select(ProposalPortalLinkModel).where(
                    ProposalPortalLinkModel.id == link_id,
                    ProposalPortalLinkModel.organization_id == self.organization_id,
                )
            )
            return self._link(model) if model else None

    def get_by_token_hash(self, token_hash: str) -> ProposalPortalLink | None:
        with self._factory() as session:
            model = session.scalar(
                select(ProposalPortalLinkModel).where(
                    ProposalPortalLinkModel.token_hash == token_hash
                )
            )
            return self._link(model) if model else None

    def list_by_proposal(self, proposal_id: int) -> tuple[ProposalPortalLink, ...]:
        if self.organization_id is None:
            return ()
        with self._factory() as session:
            return tuple(
                self._link(model)
                for model in session.scalars(
                    select(ProposalPortalLinkModel)
                    .where(
                        ProposalPortalLinkModel.organization_id == self.organization_id,
                        ProposalPortalLinkModel.proposal_id == proposal_id,
                    )
                    .order_by(
                        ProposalPortalLinkModel.created_at.desc(),
                        ProposalPortalLinkModel.id.desc(),
                    )
                )
            )

    def list_by_status(
        self, status: ProposalPortalLinkStatus
    ) -> tuple[ProposalPortalLink, ...]:
        if self.organization_id is None:
            return ()
        with self._factory() as session:
            return tuple(
                self._link(model)
                for model in session.scalars(
                    select(ProposalPortalLinkModel)
                    .where(
                        ProposalPortalLinkModel.organization_id == self.organization_id,
                        ProposalPortalLinkModel.status == status.value,
                    )
                    .order_by(ProposalPortalLinkModel.created_at.desc())
                )
            )

    def get_active_for_proposal(
        self, proposal_id: int
    ) -> tuple[ProposalPortalLink, ...]:
        return tuple(
            link
            for link in self.list_by_proposal(proposal_id)
            if link.status == ProposalPortalLinkStatus.ACTIVE
        )

    def transition(
        self,
        link_id: int,
        expected: ProposalPortalLinkStatus,
        status: ProposalPortalLinkStatus,
        user_id: int | None = None,
    ) -> ProposalPortalLink:
        with self._factory() as session, session.begin():
            predicates = [ProposalPortalLinkModel.id == link_id]
            if self.organization_id is not None:
                predicates.append(
                    ProposalPortalLinkModel.organization_id == self.organization_id
                )
            model = session.scalar(select(ProposalPortalLinkModel).where(*predicates))
            if not model or model.status != expected.value:
                raise ValueError("Invalid portal link transition.")
            model.status = status.value
            now = datetime.now(UTC)
            if status == ProposalPortalLinkStatus.ACTIVE:
                model.activated_at = now
            elif status == ProposalPortalLinkStatus.REVOKED:
                model.revoked_at, model.revoked_by_user_id = now, user_id
            elif status == ProposalPortalLinkStatus.SUPERSEDED:
                model.superseded_at = now
            session.flush()
            session.refresh(model)
            return self._link(model)

    def increment_access_count(self, link_id: int) -> ProposalPortalLink | None:
        with self._factory() as session, session.begin():
            statement = (
                update(ProposalPortalLinkModel)
                .where(
                    ProposalPortalLinkModel.id == link_id,
                    ProposalPortalLinkModel.status
                    == ProposalPortalLinkStatus.ACTIVE.value,
                    or_(
                        ProposalPortalLinkModel.max_access_count.is_(None),
                        ProposalPortalLinkModel.access_count
                        < ProposalPortalLinkModel.max_access_count,
                    ),
                )
                .values(
                    access_count=ProposalPortalLinkModel.access_count + 1,
                    last_accessed_at=datetime.now(UTC),
                )
            )
            if self.organization_id is not None:
                statement = statement.where(
                    ProposalPortalLinkModel.organization_id == self.organization_id
                )
            result = session.execute(statement)
            if result.rowcount != 1:
                return None
            model = session.get(ProposalPortalLinkModel, link_id)
            assert model is not None
            session.refresh(model)
            return self._link(model)

    def document_snapshot(
        self, link: ProposalPortalLink
    ) -> tuple[str, str, int, str, str] | None:
        with self._factory() as session:
            model = session.scalar(
                select(ProposalDocumentModel).where(
                    ProposalDocumentModel.id == link.proposal_document_id,
                    ProposalDocumentModel.organization_id == link.organization_id,
                    ProposalDocumentModel.proposal_id == link.proposal_id,
                    ProposalDocumentModel.status == "READY",
                )
            )
            if not model or not model.sha256_checksum or model.file_size_bytes is None:
                return None
            return (
                model.source_snapshot_json,
                model.storage_key,
                model.file_size_bytes,
                model.sha256_checksum,
                model.mime_type,
            )

    def create_event(
        self,
        link: ProposalPortalLink,
        event_type: ProposalPortalEventType,
        result: PortalAccessResult,
        metadata: dict[str, str | None],
        safe_metadata: dict[str, object] | None = None,
    ) -> None:
        allowed = {
            key: value
            for key, value in (safe_metadata or {}).items()
            if key in {"reason", "download", "status"}
        }
        with self._factory() as session, session.begin():
            session.add(
                ProposalPortalAccessEventModel(
                    organization_id=link.organization_id,
                    portal_link_id=link.id,
                    event_type=event_type.value,
                    access_result=result.value,
                    ip_hash=metadata.get("ip_hash"),
                    user_agent_hash=metadata.get("user_agent_hash"),
                    session_hash=metadata.get("session_hash"),
                    safe_metadata_json=json.dumps(allowed, sort_keys=True),
                )
            )

    def list_events(self, link_id: int) -> tuple[ProposalPortalAccessEvent, ...]:
        if self.organization_id is None:
            return ()
        with self._factory() as session:
            return tuple(
                ProposalPortalAccessEvent(
                    model.id,
                    model.portal_link_id,
                    ProposalPortalEventType(model.event_type),
                    PortalAccessResult(model.access_result),
                    model.ip_hash,
                    model.user_agent_hash,
                    model.session_hash,
                    json.loads(model.safe_metadata_json or "{}"),
                    model.created_at,
                )
                for model in session.scalars(
                    select(ProposalPortalAccessEventModel)
                    .join(ProposalPortalLinkModel)
                    .where(
                        ProposalPortalAccessEventModel.portal_link_id == link_id,
                        ProposalPortalLinkModel.organization_id == self.organization_id,
                    )
                    .order_by(
                        ProposalPortalAccessEventModel.created_at.desc(),
                        ProposalPortalAccessEventModel.id.desc(),
                    )
                )
            )

    def count_by_status(self) -> dict[str, int]:
        if self.organization_id is None:
            return {}
        with self._factory() as session:
            return dict(
                session.execute(
                    select(
                        ProposalPortalLinkModel.status,
                        func.count(ProposalPortalLinkModel.id),
                    )
                    .where(
                        ProposalPortalLinkModel.organization_id == self.organization_id
                    )
                    .group_by(ProposalPortalLinkModel.status)
                )
            )

    @staticmethod
    def _link(model: ProposalPortalLinkModel) -> ProposalPortalLink:
        return ProposalPortalLink(
            model.id,
            model.organization_id,
            model.proposal_id,
            model.proposal_document_id,
            ProposalPortalLinkStatus(model.status),
            model.token_hash,
            model.token_prefix,
            model.password_hash,
            model.password_required,
            model.expires_at,
            model.max_access_count,
            model.access_count,
            model.allow_pdf_download,
            model.show_pricing,
            model.created_by_user_id,
            model.revoked_by_user_id,
            model.created_at,
            model.activated_at,
            model.revoked_at,
            model.last_accessed_at,
            model.superseded_at,
        )
