from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from leadpilot.application.crm import CrmError, Page
from leadpilot.infrastructure.database.models import (
    CompanyModel,
    ContactModel,
    CrmActivityModel,
    CrmAssignmentHistoryModel,
    CrmNoteModel,
    CrmStageHistoryModel,
    CrmTaskModel,
    LeadModel,
    OpportunityModel,
    OrganizationMembershipModel,
    PipelineStageModel,
    ProposalModel,
)

MODELS = {
    "contact": ContactModel,
    "lead": LeadModel,
    "opportunity": OpportunityModel,
    "activity": CrmActivityModel,
    "task": CrmTaskModel,
    "note": CrmNoteModel,
    "stage": PipelineStageModel,
}
DEFAULT_STAGES = (
    ("Qualification", "QUALIFICATION", 10),
    ("Discovery", "DISCOVERY", 20),
    ("Solution Fit", "SOLUTION_FIT", 35),
    ("Proposal Preparation", "PROPOSAL_PREPARATION", 50),
    ("Proposal Sent", "PROPOSAL_SENT", 65),
    ("Negotiation", "NEGOTIATION", 80),
    ("Won", "WON", 100),
    ("Lost", "LOST", 0),
)


class SqlAlchemyCrmRepository:
    def __init__(self, factory: Callable[[], Session], organization_id: int) -> None:
        self.factory, self.organization_id = factory, organization_id

    def create(self, entity: str, values: dict[str, object]) -> object:
        model_type = MODELS[entity]
        values = self._serialize(values)
        values = {
            key: value
            for key, value in values.items()
            if key in model_type.__table__.columns
        }
        with self.factory() as session, session.begin():
            self._validate_relationships(session, values)
            if entity == "contact" and values.get("is_primary"):
                self._clear_primary(session, int(values["company_id"]))
            model = model_type(organization_id=self.organization_id, **values)
            session.add(model)
            session.flush()
            if entity == "opportunity":
                session.add(
                    CrmStageHistoryModel(
                        organization_id=self.organization_id,
                        opportunity_id=model.id,
                        to_stage_id=model.stage_id,
                        changed_by_user_id=values.get("created_by_user_id"),
                    )
                )
            session.refresh(model)
            return self._row(model)

    def update(self, entity: str, entity_id: int, values: dict[str, object]) -> object:
        model_type = MODELS[entity]
        with self.factory() as session, session.begin():
            model = session.scalar(
                select(model_type).where(
                    model_type.id == entity_id,
                    model_type.organization_id == self.organization_id,
                )
            )
            if not model:
                raise CrmError(f"{entity.title()} is unavailable.")
            if (
                entity in {"lead", "opportunity"}
                and model.status in {"CONVERTED", "WON", "LOST"}
                and not set(values) <= {"status", "updated_by_user_id"}
            ):
                raise CrmError("Closed CRM records are immutable.")
            self._validate_relationships(session, values)
            if entity == "contact" and values.get("is_primary"):
                self._clear_primary(session, model.company_id)
            old_owner = getattr(model, "owner_user_id", None)
            for key, value in self._serialize(values).items():
                if hasattr(model, key):
                    setattr(model, key, value)
            session.flush()
            if entity in {"lead", "opportunity"} and "owner_user_id" in values:
                session.add(
                    CrmAssignmentHistoryModel(
                        organization_id=self.organization_id,
                        entity_type=entity.upper(),
                        entity_id=model.id,
                        from_user_id=old_owner,
                        to_user_id=values["owner_user_id"],
                        assigned_by_user_id=values.get("updated_by_user_id"),
                        assignment_method=str(
                            values.get("assignment_method", "MANUAL")
                        ),
                    )
                )
            session.refresh(model)
            return self._row(model)

    def get(self, entity: str, entity_id: int) -> object | None:
        model_type = MODELS[entity]
        with self.factory() as session:
            model = session.scalar(
                select(model_type).where(
                    model_type.id == entity_id,
                    model_type.organization_id == self.organization_id,
                )
            )
            return self._row(model) if model else None

    def list(
        self,
        entity: str,
        query: str = "",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Page:
        model_type = MODELS[entity]
        page, page_size = max(page, 1), min(max(page_size, 1), 10_000)
        predicates = [model_type.organization_id == self.organization_id]
        if status and hasattr(model_type, "status"):
            predicates.append(model_type.status == status)
        if query:
            columns = [
                getattr(model_type, key)
                for key in (
                    "title",
                    "name",
                    "first_name",
                    "last_name",
                    "lead_number",
                    "opportunity_number",
                    "email",
                )
                if hasattr(model_type, key)
            ]
            predicates.append(or_(*(column.ilike(f"%{query}%") for column in columns)))
        with self.factory() as session:
            total = int(
                session.scalar(select(func.count(model_type.id)).where(*predicates))
                or 0
            )
            models = session.scalars(
                select(model_type)
                .where(*predicates)
                .order_by(model_type.created_at.desc(), model_type.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return Page(
                tuple(self._row(model) for model in models), total, page, page_size
            )

    def next_number(self, entity: str, prefix: str) -> str:
        model, column = (
            (LeadModel, LeadModel.lead_number)
            if entity == "lead"
            else (OpportunityModel, OpportunityModel.opportunity_number)
        )
        year = datetime.now(UTC).year
        with self.factory() as session:
            values = session.scalars(
                select(column).where(
                    model.organization_id == self.organization_id,
                    column.like(f"{prefix}-{year}-%"),
                )
            ).all()
        sequence = (
            max((int(value.rsplit("-", 1)[-1]) for value in values), default=0) + 1
        )
        return f"{prefix}-{year}-{sequence:04d}"

    def ensure_company(self, company_id: int) -> None:
        with self.factory() as session:
            if (
                session.scalar(
                    select(CompanyModel.id).where(
                        CompanyModel.id == company_id,
                        CompanyModel.organization_id == self.organization_id,
                    )
                )
                is None
            ):
                raise CrmError("Company is unavailable.")

    def ensure_contact(self, contact_id: int, company_id: int | None = None) -> None:
        with self.factory() as session:
            model = session.scalar(
                select(ContactModel).where(
                    ContactModel.id == contact_id,
                    ContactModel.organization_id == self.organization_id,
                )
            )
            if not model or company_id and model.company_id != company_id:
                raise CrmError("Contact does not belong to the selected company.")

    def ensure_user(self, user_id: int) -> None:
        with self.factory() as session:
            if (
                session.scalar(
                    select(OrganizationMembershipModel.id).where(
                        OrganizationMembershipModel.organization_id
                        == self.organization_id,
                        OrganizationMembershipModel.user_id == user_id,
                        OrganizationMembershipModel.status == "ACTIVE",
                    )
                )
                is None
            ):
                raise CrmError("Owner is unavailable in this organization.")

    def default_stage(self) -> object:
        with self.factory() as session, session.begin():
            stage = session.scalar(
                select(PipelineStageModel).where(
                    PipelineStageModel.organization_id == self.organization_id,
                    PipelineStageModel.is_default.is_(True),
                    PipelineStageModel.is_active.is_(True),
                )
            )
            if not stage:
                for order, (name, code, probability) in enumerate(DEFAULT_STAGES):
                    session.add(
                        PipelineStageModel(
                            organization_id=self.organization_id,
                            name=name,
                            code=code,
                            stage_type="WON"
                            if code == "WON"
                            else "LOST"
                            if code == "LOST"
                            else "OPEN",
                            probability_percentage=probability,
                            display_order=order,
                            is_active=True,
                            is_default=order == 0,
                            is_closed=code in {"WON", "LOST"},
                            is_won=code == "WON",
                            is_lost=code == "LOST",
                        )
                    )
                session.flush()
                stage = session.scalar(
                    select(PipelineStageModel).where(
                        PipelineStageModel.organization_id == self.organization_id,
                        PipelineStageModel.is_default.is_(True),
                    )
                )
            assert stage
            return self._row(stage)

    def move_stage(
        self,
        opportunity_id: int,
        stage_id: int,
        user_id: int | None,
        reason: str | None,
    ) -> object:
        with self.factory() as session, session.begin():
            opportunity = session.scalar(
                select(OpportunityModel).where(
                    OpportunityModel.id == opportunity_id,
                    OpportunityModel.organization_id == self.organization_id,
                )
            )
            stage = session.scalar(
                select(PipelineStageModel).where(
                    PipelineStageModel.id == stage_id,
                    PipelineStageModel.organization_id == self.organization_id,
                    PipelineStageModel.is_active.is_(True),
                )
            )
            if not opportunity or not stage:
                raise CrmError("Opportunity or stage is unavailable.")
            if opportunity.status != "OPEN":
                raise CrmError("Closed opportunities require an explicit reopen.")
            old = opportunity.stage_id
            opportunity.stage_id = stage.id
            opportunity.probability_percentage = stage.probability_percentage
            opportunity.weighted_amount = (
                opportunity.amount * Decimal(stage.probability_percentage) / 100
            ).quantize(Decimal("0.01"))
            if stage.is_closed:
                opportunity.status = "WON" if stage.is_won else "LOST"
                opportunity.actual_close_date = datetime.now(UTC).date()
            session.add(
                CrmStageHistoryModel(
                    organization_id=self.organization_id,
                    opportunity_id=opportunity.id,
                    from_stage_id=old,
                    to_stage_id=stage.id,
                    changed_by_user_id=user_id,
                    change_reason=reason,
                )
            )
            session.flush()
            session.refresh(opportunity)
            return self._row(opportunity)

    def convert(
        self, lead_id: int, opportunity: dict[str, object], user_id: int | None
    ) -> object:
        with self.factory() as session, session.begin():
            lead = session.scalar(
                select(LeadModel).where(
                    LeadModel.id == lead_id,
                    LeadModel.organization_id == self.organization_id,
                    LeadModel.status == "QUALIFIED",
                    LeadModel.converted_opportunity_id.is_(None),
                )
            )
            if not lead:
                raise CrmError("Lead cannot be converted.")
            model = OpportunityModel(
                organization_id=self.organization_id, **opportunity
            )
            session.add(model)
            session.flush()
            lead.status = "CONVERTED"
            lead.converted_opportunity_id = model.id
            session.add(
                CrmStageHistoryModel(
                    organization_id=self.organization_id,
                    opportunity_id=model.id,
                    to_stage_id=model.stage_id,
                    changed_by_user_id=user_id,
                )
            )
            session.refresh(model)
            return self._row(model)

    def link_proposal(self, opportunity_id: int, proposal_id: int) -> None:
        with self.factory() as session, session.begin():
            opportunity = session.scalar(
                select(OpportunityModel).where(
                    OpportunityModel.id == opportunity_id,
                    OpportunityModel.organization_id == self.organization_id,
                )
            )
            proposal = session.scalar(
                select(ProposalModel).where(
                    ProposalModel.id == proposal_id,
                    ProposalModel.organization_id == self.organization_id,
                )
            )
            if (
                not opportunity
                or not proposal
                or opportunity.company_id != proposal.company_id
            ):
                raise CrmError(
                    "Proposal and opportunity must belong to the same company."
                )
            proposal.opportunity_id = opportunity.id

    def timeline(
        self, entity: str, entity_id: int, limit: int, offset: int
    ) -> tuple[object, ...]:
        field = {
            "company": "company_id",
            "lead": "lead_id",
            "opportunity": "opportunity_id",
        }[entity]
        rows: list[SimpleNamespace] = []
        with self.factory() as session:
            for model, label, subject in (
                (CrmActivityModel, "ACTIVITY", "subject"),
                (CrmTaskModel, "TASK", "title"),
                (CrmNoteModel, "NOTE", "content"),
            ):
                for item in session.scalars(
                    select(model).where(
                        model.organization_id == self.organization_id,
                        getattr(model, field) == entity_id,
                    )
                ):
                    rows.append(
                        SimpleNamespace(
                            source=label,
                            event=getattr(item, subject)[:200],
                            created_at=item.created_at,
                        )
                    )
            if entity == "opportunity":
                for item in session.scalars(
                    select(CrmStageHistoryModel).where(
                        CrmStageHistoryModel.organization_id == self.organization_id,
                        CrmStageHistoryModel.opportunity_id == entity_id,
                    )
                ):
                    rows.append(
                        SimpleNamespace(
                            source="STAGE",
                            event="Opportunity stage changed",
                            created_at=item.created_at,
                        )
                    )
        return tuple(
            sorted(rows, key=lambda row: row.created_at, reverse=True)[
                offset : offset + limit
            ]
        )

    def metrics(self) -> dict[str, object]:
        with self.factory() as session:
            leads = dict(
                session.execute(
                    select(LeadModel.status, func.count())
                    .where(LeadModel.organization_id == self.organization_id)
                    .group_by(LeadModel.status)
                ).all()
            )
            opportunities = session.scalars(
                select(OpportunityModel).where(
                    OpportunityModel.organization_id == self.organization_id
                )
            ).all()
            tasks = session.scalars(
                select(CrmTaskModel).where(
                    CrmTaskModel.organization_id == self.organization_id
                )
            ).all()
            now = datetime.now(UTC)
            return {
                "leads": leads,
                "open_opportunities": sum(x.status == "OPEN" for x in opportunities),
                "pipeline_value": sum(
                    (x.amount for x in opportunities if x.status == "OPEN"), Decimal(0)
                ),
                "weighted_pipeline": sum(
                    (x.weighted_amount for x in opportunities if x.status == "OPEN"),
                    Decimal(0),
                ),
                "won_value": sum(
                    (x.amount for x in opportunities if x.status == "WON"), Decimal(0)
                ),
                "lost_value": sum(
                    (x.amount for x in opportunities if x.status == "LOST"), Decimal(0)
                ),
                "upcoming_tasks": sum(
                    x.status in {"OPEN", "IN_PROGRESS"} and x.due_at and x.due_at >= now
                    for x in tasks
                ),
                "overdue_tasks": sum(
                    x.status in {"OPEN", "IN_PROGRESS"} and x.due_at and x.due_at < now
                    for x in tasks
                ),
            }

    def search(self, query: str, limit: int) -> dict[str, tuple[object, ...]]:
        return {
            entity + "s": self.list(entity, query=query, page_size=limit).items
            for entity in ("contact", "lead", "opportunity")
        }

    def _validate_relationships(
        self, session: Session, values: dict[str, object]
    ) -> None:
        checks = (
            ("company_id", CompanyModel),
            ("contact_id", ContactModel),
            ("lead_id", LeadModel),
            ("opportunity_id", OpportunityModel),
            ("proposal_id", ProposalModel),
            ("stage_id", PipelineStageModel),
        )
        for key, model in checks:
            if (
                values.get(key) is not None
                and session.scalar(
                    select(model.id).where(
                        model.id == values[key],
                        model.organization_id == self.organization_id,
                    )
                )
                is None
            ):
                raise CrmError(f"Related {key.removesuffix('_id')} is unavailable.")

    def _clear_primary(self, session: Session, company_id: int) -> None:
        for model in session.scalars(
            select(ContactModel).where(
                ContactModel.organization_id == self.organization_id,
                ContactModel.company_id == company_id,
                ContactModel.is_primary.is_(True),
            )
        ):
            model.is_primary = False

    @staticmethod
    def _serialize(values: dict[str, object]) -> dict[str, object]:
        return {
            key: json.dumps(value, sort_keys=True)
            if key.endswith("_json") and not isinstance(value, str)
            else value
            for key, value in values.items()
            if key not in {"assignment_method"}
        }

    @staticmethod
    def _row(model: object) -> object:
        return SimpleNamespace(
            **{
                column.name: getattr(model, column.name)
                for column in model.__table__.columns
            }
        )
