from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from leadpilot.application.sales_intelligence import (
    IntelligencePage,
    SalesIntelligenceError,
)
from leadpilot.infrastructure.database.models import (
    CrmActivityModel,
    CrmTaskModel,
    LeadIntelligenceScoreModel,
    LeadModel,
    OpportunityForecastSnapshotModel,
    OpportunityHealthScoreModel,
    OpportunityModel,
    RevenueForecastModel,
    SalesIntelligenceConfigModel,
    SalesRecommendationModel,
    WinLossAnalysisModel,
)


class SqlAlchemySalesIntelligenceRepository:
    def __init__(self, factory: Callable[[], Session], organization_id: int) -> None:
        self.factory, self.organization_id = factory, organization_id

    def get_config(self) -> object | None:
        with self.factory() as session:
            model = session.scalar(
                select(SalesIntelligenceConfigModel).where(
                    SalesIntelligenceConfigModel.organization_id
                    == self.organization_id,
                    SalesIntelligenceConfigModel.is_active.is_(True),
                )
            )
            return self._row(model) if model else None

    def save_config(self, values: dict[str, object]) -> object:
        with self.factory() as session, session.begin():
            model = session.scalar(
                select(SalesIntelligenceConfigModel).where(
                    SalesIntelligenceConfigModel.organization_id == self.organization_id
                )
            )
            if not model:
                model = SalesIntelligenceConfigModel(
                    organization_id=self.organization_id
                )
                session.add(model)
            for key, value in values.items():
                if hasattr(model, key):
                    setattr(
                        model,
                        key,
                        json.dumps(value)
                        if key == "weights_json" and not isinstance(value, str)
                        else value,
                    )
            session.flush()
            session.refresh(model)
            return self._row(model)

    def entity_snapshot(self, entity: str, entity_id: int) -> dict[str, object]:
        model = LeadModel if entity == "LEAD" else OpportunityModel
        with self.factory() as session:
            row = session.scalar(
                select(model).where(
                    model.id == entity_id, model.organization_id == self.organization_id
                )
            )
            if not row:
                raise SalesIntelligenceError(f"{entity.title()} is unavailable.")
            return self._snapshot(session, entity, row)

    def list_entity_snapshots(self, entity: str) -> tuple[dict[str, object], ...]:
        model = LeadModel if entity == "LEAD" else OpportunityModel
        with self.factory() as session:
            rows = session.scalars(
                select(model).where(model.organization_id == self.organization_id)
            ).all()
            return tuple(self._snapshot(session, entity, row) for row in rows)

    def save_score(self, entity: str, values: dict[str, object]) -> object:
        model_type = (
            LeadIntelligenceScoreModel
            if entity == "LEAD"
            else OpportunityHealthScoreModel
        )
        with self.factory() as session, session.begin():
            model = model_type(
                organization_id=self.organization_id, **self._serialize(values)
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._row(model)

    def latest_score(self, entity: str, entity_id: int) -> object | None:
        model, field = (
            (LeadIntelligenceScoreModel, LeadIntelligenceScoreModel.lead_id)
            if entity == "LEAD"
            else (
                OpportunityHealthScoreModel,
                OpportunityHealthScoreModel.opportunity_id,
            )
        )
        with self.factory() as session:
            row = session.scalar(
                select(model)
                .where(
                    model.organization_id == self.organization_id, field == entity_id
                )
                .order_by(model.calculated_at.desc(), model.id.desc())
            )
            return self._row(row) if row else None

    def score_history(self, entity: str, entity_id: int) -> tuple[object, ...]:
        model, field = (
            (LeadIntelligenceScoreModel, LeadIntelligenceScoreModel.lead_id)
            if entity == "LEAD"
            else (
                OpportunityHealthScoreModel,
                OpportunityHealthScoreModel.opportunity_id,
            )
        )
        with self.factory() as session:
            return tuple(
                self._row(x)
                for x in session.scalars(
                    select(model)
                    .where(
                        model.organization_id == self.organization_id,
                        field == entity_id,
                    )
                    .order_by(model.calculated_at.desc())
                )
            )

    def create_recommendation(self, values: dict[str, object]) -> object:
        self.entity_snapshot(str(values["entity_type"]), int(values["entity_id"]))
        with self.factory() as session, session.begin():
            existing = session.scalar(
                select(SalesRecommendationModel).where(
                    SalesRecommendationModel.organization_id == self.organization_id,
                    SalesRecommendationModel.entity_type == values["entity_type"],
                    SalesRecommendationModel.entity_id == values["entity_id"],
                    SalesRecommendationModel.recommendation_type
                    == values["recommendation_type"],
                    SalesRecommendationModel.source_snapshot_hash
                    == values["source_snapshot_hash"],
                )
            )
            if existing:
                return self._row(existing)
            model = SalesRecommendationModel(
                organization_id=self.organization_id, **self._serialize(values)
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._row(model)

    def get_recommendation(self, recommendation_id: int) -> object:
        with self.factory() as session:
            model = session.scalar(
                select(SalesRecommendationModel).where(
                    SalesRecommendationModel.id == recommendation_id,
                    SalesRecommendationModel.organization_id == self.organization_id,
                )
            )
            if not model:
                raise SalesIntelligenceError("Recommendation is unavailable.")
            return self._row(model)

    def update_recommendation(
        self, recommendation_id: int, values: dict[str, object]
    ) -> object:
        with self.factory() as session, session.begin():
            model = session.scalar(
                select(SalesRecommendationModel).where(
                    SalesRecommendationModel.id == recommendation_id,
                    SalesRecommendationModel.organization_id == self.organization_id,
                )
            )
            if not model:
                raise SalesIntelligenceError("Recommendation is unavailable.")
            for key, value in values.items():
                setattr(model, key, value)
            session.flush()
            session.refresh(model)
            return self._row(model)

    def list_recommendations(self, **filters: object) -> IntelligencePage:
        predicates = [SalesRecommendationModel.organization_id == self.organization_id]
        for key in ("status", "priority", "entity_type", "recommendation_type"):
            if filters.get(key):
                predicates.append(
                    getattr(SalesRecommendationModel, key) == filters[key]
                )
        page, size = (
            max(1, int(filters.get("page", 1))),
            min(500, max(1, int(filters.get("page_size", 50)))),
        )
        with self.factory() as session:
            total = int(
                session.scalar(
                    select(func.count(SalesRecommendationModel.id)).where(*predicates)
                )
                or 0
            )
            rows = session.scalars(
                select(SalesRecommendationModel)
                .where(*predicates)
                .order_by(SalesRecommendationModel.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
            return IntelligencePage(tuple(self._row(x) for x in rows), total)

    def create_task_or_activity(
        self, recommendation: object, entity: str, user_id: int | None
    ) -> object:
        entity_field = (
            "lead_id" if recommendation.entity_type == "LEAD" else "opportunity_id"
        )
        model_type = CrmActivityModel if entity == "activity" else CrmTaskModel
        values = {
            entity_field: recommendation.entity_id,
            "organization_id": self.organization_id,
        }
        if entity == "activity":
            values.update(
                activity_type=recommendation.recommendation_type,
                subject=recommendation.title,
                description=recommendation.description,
                status="PLANNED",
                owner_user_id=user_id,
            )
        else:
            values.update(
                title=recommendation.title,
                description=recommendation.description,
                status="OPEN",
                priority=recommendation.priority,
                assigned_to_user_id=user_id,
                created_by_user_id=user_id,
                due_at=recommendation.suggested_due_at,
            )
        with self.factory() as session, session.begin():
            model = model_type(**values)
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._row(model)

    def create_forecasts(
        self, forecasts: tuple[dict[str, object], ...]
    ) -> tuple[object, ...]:
        output = []
        with self.factory() as session, session.begin():
            for values in forecasts:
                snapshots = values.pop("snapshots")
                model = RevenueForecastModel(
                    organization_id=self.organization_id, **self._serialize(values)
                )
                session.add(model)
                session.flush()
                for item in snapshots:
                    probability = int(item["probability_percentage"])
                    status = str(item["status"])
                    session.add(
                        OpportunityForecastSnapshotModel(
                            organization_id=self.organization_id,
                            revenue_forecast_id=model.id,
                            opportunity_id=item["id"],
                            stage_id=item["stage_id"],
                            status=status,
                            currency=item["currency"],
                            amount=item["amount"],
                            probability_percentage=probability,
                            weighted_amount=Decimal(str(item["amount"]))
                            * probability
                            / 100,
                            expected_close_date=item.get("expected_close_date"),
                            forecast_category="CLOSED_WON"
                            if status == "WON"
                            else "COMMIT"
                            if probability >= 75
                            else "BEST_CASE"
                            if probability >= 50
                            else "PIPELINE",
                            risk_level="HIGH" if item.get("overdue_tasks") else "LOW",
                            included_in_commit=probability >= 75,
                            included_in_best_case=probability >= 50,
                            included_in_worst_case=status == "WON" or probability >= 75,
                        )
                    )
                session.flush()
                session.refresh(model)
                output.append(self._row(model))
        return tuple(output)

    def list_forecasts(self) -> tuple[object, ...]:
        with self.factory() as session:
            return tuple(
                self._row(x)
                for x in session.scalars(
                    select(RevenueForecastModel)
                    .where(RevenueForecastModel.organization_id == self.organization_id)
                    .order_by(RevenueForecastModel.created_at.desc())
                )
            )

    def create_win_loss(
        self, opportunity_id: int, reason: str, user_id: int | None
    ) -> object:
        source = self.entity_snapshot("OPPORTUNITY", opportunity_id)
        if source["status"] not in {"WON", "LOST"}:
            raise SalesIntelligenceError("Only closed opportunities can be analyzed.")
        with self.factory() as session, session.begin():
            proposal_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(
                        __import__(
                            "leadpilot.infrastructure.database.models",
                            fromlist=["ProposalModel"],
                        ).ProposalModel
                    )
                    .where(
                        __import__(
                            "leadpilot.infrastructure.database.models",
                            fromlist=["ProposalModel"],
                        ).ProposalModel.organization_id
                        == self.organization_id,
                        __import__(
                            "leadpilot.infrastructure.database.models",
                            fromlist=["ProposalModel"],
                        ).ProposalModel.opportunity_id
                        == opportunity_id,
                    )
                )
                or 0
            )
            activity_count = int(
                session.scalar(
                    select(func.count(CrmActivityModel.id)).where(
                        CrmActivityModel.organization_id == self.organization_id,
                        CrmActivityModel.opportunity_id == opportunity_id,
                    )
                )
                or 0
            )
            created = source["created_at"]
            closed = source.get("actual_close_date")
            model = WinLossAnalysisModel(
                organization_id=self.organization_id,
                opportunity_id=opportunity_id,
                outcome=source["status"],
                primary_reason=reason or "Not specified",
                amount=source["amount"],
                currency=source["currency"],
                sales_cycle_days=(closed - created.date()).days if closed else None,
                proposal_count=proposal_count,
                activity_count=activity_count,
                engagement_summary_json="{}",
                analyzed_at=datetime.now(UTC),
                analyzed_by_user_id=user_id,
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._row(model)

    def team_metrics(self) -> tuple[dict[str, object], ...]:
        with self.factory() as session:
            leads = session.scalars(
                select(LeadModel).where(
                    LeadModel.organization_id == self.organization_id
                )
            ).all()
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
        owners = {x.owner_user_id for x in (*leads, *opportunities)} | {None}
        return tuple(
            {
                "owner": owner if owner is not None else "Unassigned",
                "leads": sum(x.owner_user_id == owner for x in leads),
                "qualified_leads": sum(
                    x.owner_user_id == owner and x.status in {"QUALIFIED", "CONVERTED"}
                    for x in leads
                ),
                "open_pipeline": sum(
                    (
                        x.amount
                        for x in opportunities
                        if x.owner_user_id == owner and x.status == "OPEN"
                    ),
                    Decimal(),
                ),
                "weighted_pipeline": sum(
                    (
                        x.weighted_amount
                        for x in opportunities
                        if x.owner_user_id == owner and x.status == "OPEN"
                    ),
                    Decimal(),
                ),
                "won": sum(
                    (
                        x.amount
                        for x in opportunities
                        if x.owner_user_id == owner and x.status == "WON"
                    ),
                    Decimal(),
                ),
                "lost": sum(
                    (
                        x.amount
                        for x in opportunities
                        if x.owner_user_id == owner and x.status == "LOST"
                    ),
                    Decimal(),
                ),
                "task_completion_rate": round(
                    100
                    * sum(
                        x.assigned_to_user_id == owner and x.status == "COMPLETED"
                        for x in tasks
                    )
                    / max(1, sum(x.assigned_to_user_id == owner for x in tasks)),
                    1,
                ),
            }
            for owner in owners
        )

    def _snapshot(
        self, session: Session, entity: str, row: object
    ) -> dict[str, object]:
        result = {
            column.name: getattr(row, column.name) for column in row.__table__.columns
        }
        result["safe_reference"] = getattr(row, "lead_number", None) or getattr(
            row, "opportunity_number", None
        )
        if entity == "LEAD":
            result["last_activity_at"] = session.scalar(
                select(func.max(CrmActivityModel.completed_at)).where(
                    CrmActivityModel.organization_id == self.organization_id,
                    CrmActivityModel.lead_id == row.id,
                )
            )
            result["discovery_completed"] = row.source == "DISCOVERY"
            result["proposal_engagement"] = 0
        else:
            result["overdue_tasks"] = int(
                session.scalar(
                    select(func.count(CrmTaskModel.id)).where(
                        CrmTaskModel.organization_id == self.organization_id,
                        CrmTaskModel.opportunity_id == row.id,
                        CrmTaskModel.status == "OPEN",
                        CrmTaskModel.due_at < datetime.now(UTC),
                    )
                )
                or 0
            )
            result["proposal_engagement"] = 0
        return result

    @staticmethod
    def _serialize(values: dict[str, object]) -> dict[str, object]:
        return {
            key: json.dumps(value, default=str)
            if key.endswith("_json") and not isinstance(value, str)
            else value
            for key, value in values.items()
        }

    @staticmethod
    def _row(model: object) -> object:
        values = {
            column.name: getattr(model, column.name)
            for column in model.__table__.columns
        }
        for key, value in tuple(values.items()):
            if key.endswith("_json") and isinstance(value, str):
                try:
                    values[key] = json.loads(value)
                except json.JSONDecodeError:
                    pass
        return SimpleNamespace(**values)
