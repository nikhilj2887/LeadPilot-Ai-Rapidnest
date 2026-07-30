from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadpilot.application.proposals import (
    Proposal,
    ProposalActivity,
    ProposalFilters,
    ProposalItem,
    ProposalItemInput,
    ProposalItemType,
    ProposalMetrics,
    ProposalPage,
    ProposalSection,
    ProposalSectionInput,
    ProposalSort,
    ProposalStatus,
    ProposalValidationError,
    ProposalVersion,
)
from leadpilot.infrastructure.database.models import (
    CompanyModel,
    DiscoveryScanModel,
    OrganizationServiceModel,
    ProposalActivityModel,
    ProposalItemModel,
    ProposalModel,
    ProposalSectionModel,
    ProposalVersionModel,
)


class SqlAlchemyProposalRepository:
    """SQLAlchemy persistence whose every operation is bound to one tenant."""

    def __init__(
        self, session_factory: Callable[[], Session], organization_id: int
    ) -> None:
        self._session_factory = session_factory
        self.organization_id = organization_id

    def company_exists(self, company_id: int) -> bool:
        with self._session_factory() as session:
            return (
                session.scalar(
                    select(CompanyModel.id).where(
                        CompanyModel.id == company_id,
                        CompanyModel.organization_id == self.organization_id,
                    )
                )
                is not None
            )

    def scan_company_id(self, scan_id: int) -> int | None:
        with self._session_factory() as session:
            return session.scalar(
                select(DiscoveryScanModel.company_id).where(
                    DiscoveryScanModel.id == scan_id,
                    DiscoveryScanModel.organization_id == self.organization_id,
                )
            )

    def catalog_item(
        self, item_id: int
    ) -> tuple[str, str | None, Decimal | None, str, bool] | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(OrganizationServiceModel).where(
                    OrganizationServiceModel.id == item_id,
                    OrganizationServiceModel.organization_id == self.organization_id,
                )
            )
            if model is None:
                return None
            return (
                model.name,
                model.detailed_description or model.short_description,
                model.base_price,
                model.currency,
                model.is_active,
            )

    def next_number(self, year: int) -> str:
        prefix = f"LP-{year}-"
        with self._session_factory() as session:
            numbers = session.scalars(
                select(ProposalModel.proposal_number).where(
                    ProposalModel.organization_id == self.organization_id,
                    ProposalModel.proposal_number.like(f"{prefix}%"),
                )
            )
            sequence = max(
                (
                    int(number.removeprefix(prefix))
                    for number in numbers
                    if number.removeprefix(prefix).isdigit()
                ),
                default=0,
            )
        return f"{prefix}{sequence + 1:04d}"

    def create(self, values: Any, number: str, user_id: int | None) -> Proposal:
        with self._session_factory() as session, session.begin():
            model = ProposalModel(
                organization_id=self.organization_id,
                proposal_number=number,
                status=ProposalStatus.DRAFT.value,
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
                **values.model_dump(),
            )
            session.add(model)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ProposalValidationError(
                    "Could not allocate a unique proposal number; retry the request"
                ) from exc
            session.refresh(model)
            return self._proposal(model, self._company_name(session, model.company_id))

    def get(self, proposal_id: int) -> Proposal | None:
        with self._session_factory() as session:
            model = self._tenant_proposal(session, proposal_id)
            return (
                self._proposal(model, self._company_name(session, model.company_id))
                if model
                else None
            )

    def update(
        self, proposal_id: int, values: Any, user_id: int | None
    ) -> Proposal | None:
        with self._session_factory() as session, session.begin():
            model = self._tenant_proposal(session, proposal_id)
            if model is None:
                return None
            for name, value in values.model_dump().items():
                setattr(model, name, value)
            model.updated_by_user_id = user_id
            session.flush()
            session.refresh(model)
            return self._proposal(model, self._company_name(session, model.company_id))

    def delete(self, proposal_id: int) -> bool:
        with self._session_factory() as session, session.begin():
            model = self._tenant_proposal(session, proposal_id)
            if model is None:
                return False
            session.delete(model)
            return True

    def transition(
        self, proposal_id: int, status: ProposalStatus, user_id: int | None
    ) -> Proposal | None:
        with self._session_factory() as session, session.begin():
            model = self._tenant_proposal(session, proposal_id)
            if model is None:
                return None
            model.status = status.value
            model.updated_by_user_id = user_id
            now = datetime.now(UTC)
            timestamp_fields = {
                ProposalStatus.APPROVED: "approved_at",
                ProposalStatus.SENT: "sent_at",
                ProposalStatus.ACCEPTED: "accepted_at",
                ProposalStatus.REJECTED: "rejected_at",
                ProposalStatus.EXPIRED: "expired_at",
            }
            field = timestamp_fields.get(status)
            if field:
                setattr(model, field, now)
            if status == ProposalStatus.APPROVED:
                model.approved_by_user_id = user_id
            session.flush()
            session.refresh(model)
            return self._proposal(model, self._company_name(session, model.company_id))

    def list(
        self,
        filters: ProposalFilters,
        *,
        page: int,
        page_size: int,
        sort: ProposalSort,
        descending: bool,
    ) -> ProposalPage:
        predicates = self._predicates(filters)
        sort_column = {
            ProposalSort.UPDATED: ProposalModel.updated_at,
            ProposalSort.CREATED: ProposalModel.created_at,
            ProposalSort.NUMBER: ProposalModel.proposal_number,
            ProposalSort.TITLE: ProposalModel.title,
            ProposalSort.TOTAL: ProposalModel.total_amount,
        }[sort]
        direction = desc if descending else asc
        statement = (
            select(ProposalModel, CompanyModel.name)
            .join(CompanyModel, CompanyModel.id == ProposalModel.company_id)
            .where(*predicates)
            .order_by(direction(sort_column), direction(ProposalModel.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        with self._session_factory() as session:
            total = (
                session.scalar(select(func.count(ProposalModel.id)).where(*predicates))
                or 0
            )
            items = tuple(
                self._proposal(model, company_name)
                for model, company_name in session.execute(statement)
            )
        return ProposalPage(items, total, page, page_size)

    def metrics(self) -> ProposalMetrics:
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    ProposalModel.status,
                    func.count(ProposalModel.id),
                    func.coalesce(func.sum(ProposalModel.total_amount), 0),
                )
                .where(ProposalModel.organization_id == self.organization_id)
                .group_by(ProposalModel.status)
            )
            values = {status: (count, Decimal(total)) for status, count, total in rows}
        pipeline = sum(
            total
            for status, (_, total) in values.items()
            if status
            not in {ProposalStatus.ARCHIVED.value, ProposalStatus.REJECTED.value}
        )
        return ProposalMetrics(
            total=sum(count for count, _ in values.values()),
            drafts=values.get(ProposalStatus.DRAFT.value, (0, Decimal(0)))[0],
            in_review=values.get(ProposalStatus.IN_REVIEW.value, (0, Decimal(0)))[0],
            accepted=values.get(ProposalStatus.ACCEPTED.value, (0, Decimal(0)))[0],
            pipeline_value=pipeline,
        )

    def add_item(
        self,
        proposal_id: int,
        values: ProposalItemInput,
        catalog_id: int | None,
    ) -> ProposalItem:
        with self._session_factory() as session, session.begin():
            self._require_proposal(session, proposal_id)
            subtotal, tax, total = self._line(values)
            model = ProposalItemModel(
                organization_id=self.organization_id,
                proposal_id=proposal_id,
                service_catalog_id=catalog_id,
                line_subtotal=subtotal,
                line_tax=tax,
                line_total=total,
                **self._item_values(values),
            )
            session.add(model)
            session.flush()
            self._recalculate(session, proposal_id)
            session.refresh(model)
            return self._item(model)

    def update_item(
        self, proposal_id: int, item_id: int, values: ProposalItemInput
    ) -> ProposalItem | None:
        with self._session_factory() as session, session.begin():
            model = self._tenant_item(session, proposal_id, item_id)
            if model is None:
                return None
            subtotal, tax, total = self._line(values)
            for key, value in self._item_values(values).items():
                setattr(model, key, value)
            model.line_subtotal, model.line_tax, model.line_total = subtotal, tax, total
            self._recalculate(session, proposal_id)
            session.flush()
            session.refresh(model)
            return self._item(model)

    def delete_item(self, proposal_id: int, item_id: int) -> bool:
        with self._session_factory() as session, session.begin():
            model = self._tenant_item(session, proposal_id, item_id)
            if model is None:
                return False
            session.delete(model)
            session.flush()
            self._recalculate(session, proposal_id)
            return True

    def list_items(self, proposal_id: int) -> tuple[ProposalItem, ...]:
        with self._session_factory() as session:
            if self._tenant_proposal(session, proposal_id) is None:
                return ()
            return tuple(
                self._item(model)
                for model in session.scalars(
                    select(ProposalItemModel)
                    .where(
                        ProposalItemModel.proposal_id == proposal_id,
                        ProposalItemModel.organization_id == self.organization_id,
                    )
                    .order_by(ProposalItemModel.display_order, ProposalItemModel.id)
                )
            )

    def reorder_items(self, proposal_id: int, item_ids: list[int]) -> bool:
        with self._session_factory() as session, session.begin():
            models = list(
                session.scalars(
                    select(ProposalItemModel).where(
                        ProposalItemModel.proposal_id == proposal_id,
                        ProposalItemModel.organization_id == self.organization_id,
                    )
                )
            )
            if len(item_ids) != len(models) or set(item_ids) != {m.id for m in models}:
                return False
            by_id = {model.id: model for model in models}
            for order, item_id in enumerate(item_ids):
                by_id[item_id].display_order = order
            return True

    def add_section(
        self,
        proposal_id: int,
        key: str,
        values: ProposalSectionInput,
    ) -> ProposalSection:
        with self._session_factory() as session, session.begin():
            self._require_proposal(session, proposal_id)
            model = ProposalSectionModel(
                organization_id=self.organization_id,
                proposal_id=proposal_id,
                section_key=key,
                **values.model_dump(),
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._section(model)

    def update_section(
        self, proposal_id: int, section_id: int, values: ProposalSectionInput
    ) -> ProposalSection | None:
        with self._session_factory() as session, session.begin():
            model = session.scalar(
                select(ProposalSectionModel).where(
                    ProposalSectionModel.id == section_id,
                    ProposalSectionModel.proposal_id == proposal_id,
                    ProposalSectionModel.organization_id == self.organization_id,
                )
            )
            if model is None:
                return None
            for key, value in values.model_dump().items():
                setattr(model, key, value)
            model.manually_edited = True
            model.content_source = (
                "AI_GENERATED_THEN_EDITED"
                if model.content_source == "AI_GENERATED"
                else "MANUAL"
            )
            session.flush()
            session.refresh(model)
            return self._section(model)

    def list_sections(self, proposal_id: int) -> tuple[ProposalSection, ...]:
        with self._session_factory() as session:
            if self._tenant_proposal(session, proposal_id) is None:
                return ()
            return tuple(
                self._section(model)
                for model in session.scalars(
                    select(ProposalSectionModel)
                    .where(
                        ProposalSectionModel.proposal_id == proposal_id,
                        ProposalSectionModel.organization_id == self.organization_id,
                    )
                    .order_by(
                        ProposalSectionModel.display_order, ProposalSectionModel.id
                    )
                )
            )

    def reorder_sections(self, proposal_id: int, section_ids: list[int]) -> bool:
        with self._session_factory() as session, session.begin():
            models = list(
                session.scalars(
                    select(ProposalSectionModel).where(
                        ProposalSectionModel.proposal_id == proposal_id,
                        ProposalSectionModel.organization_id == self.organization_id,
                    )
                )
            )
            if len(section_ids) != len(models) or set(section_ids) != {
                model.id for model in models
            }:
                return False
            by_id = {model.id: model for model in models}
            for order, section_id in enumerate(section_ids):
                by_id[section_id].display_order = order
            return True

    def create_version(
        self,
        proposal_id: int,
        snapshot: dict[str, Any],
        summary: str | None,
        user_id: int | None,
    ) -> ProposalVersion:
        with self._session_factory() as session, session.begin():
            self._require_proposal(session, proposal_id)
            current = (
                session.scalar(
                    select(func.max(ProposalVersionModel.version_number)).where(
                        ProposalVersionModel.proposal_id == proposal_id,
                        ProposalVersionModel.organization_id == self.organization_id,
                    )
                )
                or 0
            )
            model = ProposalVersionModel(
                organization_id=self.organization_id,
                proposal_id=proposal_id,
                version_number=current + 1,
                snapshot_json=json.dumps(snapshot, sort_keys=True),
                change_summary=summary,
                created_by_user_id=user_id,
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._version(model)

    def list_versions(self, proposal_id: int) -> tuple[ProposalVersion, ...]:
        with self._session_factory() as session:
            if self._tenant_proposal(session, proposal_id) is None:
                return ()
            return tuple(
                self._version(model)
                for model in session.scalars(
                    select(ProposalVersionModel)
                    .where(
                        ProposalVersionModel.proposal_id == proposal_id,
                        ProposalVersionModel.organization_id == self.organization_id,
                    )
                    .order_by(ProposalVersionModel.version_number.desc())
                )
            )

    def add_activity(
        self,
        proposal_id: int,
        activity_type: str,
        details: dict[str, Any],
        user_id: int | None,
    ) -> None:
        with self._session_factory() as session, session.begin():
            self._require_proposal(session, proposal_id)
            session.add(
                ProposalActivityModel(
                    organization_id=self.organization_id,
                    proposal_id=proposal_id,
                    user_id=user_id,
                    activity_type=activity_type,
                    details_json=json.dumps(details, sort_keys=True),
                )
            )

    def list_activities(self, proposal_id: int) -> tuple[ProposalActivity, ...]:
        with self._session_factory() as session:
            if self._tenant_proposal(session, proposal_id) is None:
                return ()
            return tuple(
                self._activity(model)
                for model in session.scalars(
                    select(ProposalActivityModel)
                    .where(
                        ProposalActivityModel.proposal_id == proposal_id,
                        ProposalActivityModel.organization_id == self.organization_id,
                    )
                    .order_by(
                        ProposalActivityModel.created_at.desc(),
                        ProposalActivityModel.id.desc(),
                    )
                )
            )

    def _predicates(self, filters: ProposalFilters) -> list[Any]:
        predicates: list[Any] = [ProposalModel.organization_id == self.organization_id]
        if filters.query.strip():
            pattern = f"%{filters.query.strip().casefold()}%"
            predicates.append(
                or_(
                    func.lower(ProposalModel.title).like(pattern),
                    func.lower(ProposalModel.proposal_number).like(pattern),
                )
            )
        if filters.company_id:
            predicates.append(ProposalModel.company_id == filters.company_id)
        if filters.status:
            predicates.append(ProposalModel.status == filters.status.value)
        if filters.created_from:
            predicates.append(
                func.date(ProposalModel.created_at) >= filters.created_from
            )
        if filters.created_to:
            predicates.append(func.date(ProposalModel.created_at) <= filters.created_to)
        return predicates

    def _tenant_proposal(
        self, session: Session, proposal_id: int
    ) -> ProposalModel | None:
        return session.scalar(
            select(ProposalModel).where(
                ProposalModel.id == proposal_id,
                ProposalModel.organization_id == self.organization_id,
            )
        )

    def _require_proposal(self, session: Session, proposal_id: int) -> ProposalModel:
        model = self._tenant_proposal(session, proposal_id)
        if model is None:
            raise ProposalValidationError(
                "Proposal is unavailable in this organization"
            )
        return model

    def _tenant_item(
        self, session: Session, proposal_id: int, item_id: int
    ) -> ProposalItemModel | None:
        return session.scalar(
            select(ProposalItemModel).where(
                ProposalItemModel.id == item_id,
                ProposalItemModel.proposal_id == proposal_id,
                ProposalItemModel.organization_id == self.organization_id,
            )
        )

    def _recalculate(self, session: Session, proposal_id: int) -> None:
        proposal = self._require_proposal(session, proposal_id)
        totals = session.execute(
            select(
                func.coalesce(func.sum(ProposalItemModel.line_subtotal), 0),
                func.coalesce(func.sum(ProposalItemModel.discount_amount), 0),
                func.coalesce(func.sum(ProposalItemModel.line_tax), 0),
                func.coalesce(func.sum(ProposalItemModel.line_total), 0),
            ).where(
                ProposalItemModel.proposal_id == proposal_id,
                ProposalItemModel.organization_id == self.organization_id,
                ProposalItemModel.is_optional.is_(False),
            )
        ).one()
        (
            proposal.subtotal,
            proposal.discount_amount,
            proposal.tax_amount,
            proposal.total_amount,
        ) = (Decimal(value) for value in totals)

    @staticmethod
    def _line(values: ProposalItemInput) -> tuple[Decimal, Decimal, Decimal]:
        from leadpilot.application.proposals import ProposalService

        return ProposalService.calculate_line(values)

    @staticmethod
    def _item_values(values: ProposalItemInput) -> dict[str, Any]:
        result = values.model_dump()
        result["item_type"] = values.item_type.value
        return result

    @staticmethod
    def _company_name(session: Session, company_id: int) -> str:
        return (
            session.scalar(
                select(CompanyModel.name).where(CompanyModel.id == company_id)
            )
            or "Unknown company"
        )

    @staticmethod
    def _proposal(model: ProposalModel, company_name: str) -> Proposal:
        return Proposal(
            id=model.id,
            organization_id=model.organization_id,
            company_id=model.company_id,
            company_name=company_name,
            discovery_scan_id=model.discovery_scan_id,
            proposal_number=model.proposal_number,
            title=model.title,
            status=ProposalStatus(model.status),
            currency=model.currency,
            valid_until=model.valid_until,
            summary=model.summary,
            client_requirements=model.client_requirements,
            recommended_approach=model.recommended_approach,
            implementation_plan=model.implementation_plan,
            commercial_notes=model.commercial_notes,
            terms_and_conditions=model.terms_and_conditions,
            internal_notes=model.internal_notes,
            subtotal=model.subtotal,
            discount_amount=model.discount_amount,
            tax_amount=model.tax_amount,
            total_amount=model.total_amount,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _item(model: ProposalItemModel) -> ProposalItem:
        return ProposalItem(
            id=model.id,
            proposal_id=model.proposal_id,
            service_catalog_id=model.service_catalog_id,
            item_type=ProposalItemType(model.item_type),
            title=model.title,
            description=model.description,
            quantity=model.quantity,
            unit_price=model.unit_price,
            discount_amount=model.discount_amount,
            tax_rate=model.tax_rate,
            line_subtotal=model.line_subtotal,
            line_tax=model.line_tax,
            line_total=model.line_total,
            delivery_timeline=model.delivery_timeline,
            selection_reason=model.selection_reason,
            is_optional=model.is_optional,
            display_order=model.display_order,
        )

    @staticmethod
    def _section(model: ProposalSectionModel) -> ProposalSection:
        return ProposalSection(
            id=model.id,
            proposal_id=model.proposal_id,
            section_key=model.section_key,
            title=model.title,
            content=model.content,
            is_enabled=model.is_enabled,
            display_order=model.display_order,
            content_source=model.content_source,
            last_ai_run_id=model.last_ai_run_id,
            manually_edited=model.manually_edited,
            generated_at=model.generated_at,
        )

    @staticmethod
    def _version(model: ProposalVersionModel) -> ProposalVersion:
        return ProposalVersion(
            id=model.id,
            proposal_id=model.proposal_id,
            version_number=model.version_number,
            snapshot=json.loads(model.snapshot_json),
            change_summary=model.change_summary,
            created_at=model.created_at,
        )

    @staticmethod
    def _activity(model: ProposalActivityModel) -> ProposalActivity:
        return ProposalActivity(
            id=model.id,
            proposal_id=model.proposal_id,
            activity_type=model.activity_type,
            details=json.loads(model.details_json),
            created_at=model.created_at,
        )
