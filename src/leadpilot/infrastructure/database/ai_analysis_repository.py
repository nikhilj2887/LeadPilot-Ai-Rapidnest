from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from leadpilot.application.discovery import utcnow
from leadpilot.application.discovery_ai import AI_STATUSES, DiscoveryAIAnalysis
from leadpilot.infrastructure.database.models import DiscoveryAIAnalysisModel

JSON_FIELDS = {
    "digital_strengths",
    "improvement_areas",
    "business_risks",
    "quick_wins",
    "strategic_opportunities",
    "recommended_services",
    "implementation_roadmap",
    "discovery_questions",
    "outreach_angles",
    "evidence_references",
    "raw_response_metadata",
}


class AIAnalysisRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def create(self, **values: Any) -> DiscoveryAIAnalysis:
        with self._session_factory() as session, session.begin():
            model = DiscoveryAIAnalysisModel(**values)
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._detach(session, model)

    def update_status(self, analysis_id: int, status: str) -> DiscoveryAIAnalysis:
        if status not in AI_STATUSES:
            raise ValueError("Invalid AI analysis status")
        with self._session_factory() as session, session.begin():
            model = self._required(session, analysis_id)
            allowed = {
                "Pending": {"Running", "Failed"},
                "Running": {"Completed", "Failed"},
                "Completed": set(),
                "Failed": set(),
            }
            if status != model.status and status not in allowed[model.status]:
                raise ValueError("Invalid AI analysis status transition")
            model.status = status
            if status == "Running":
                model.generated_at = utcnow()
            session.flush()
            session.refresh(model)
            return self._detach(session, model)

    def save_completed(self, analysis_id: int, **values: Any) -> DiscoveryAIAnalysis:
        with self._session_factory() as session, session.begin():
            model = self._required(session, analysis_id)
            if model.status != "Running":
                raise ValueError("Only a running analysis can be completed")
            for key, value in values.items():
                if hasattr(model, key):
                    setattr(
                        model, key, json.dumps(value) if key in JSON_FIELDS else value
                    )
            model.status, model.completed_at, model.error_message = (
                "Completed",
                utcnow(),
                None,
            )
            session.flush()
            session.refresh(model)
            return self._detach(session, model)

    def save_failed(self, analysis_id: int, message: str) -> DiscoveryAIAnalysis:
        with self._session_factory() as session, session.begin():
            model = self._required(session, analysis_id)
            model.status, model.completed_at = "Failed", utcnow()
            model.error_message = (message.strip() or "AI generation failed.")[:1000]
            session.flush()
            session.refresh(model)
            return self._detach(session, model)

    def get_by_id(self, analysis_id: int) -> DiscoveryAIAnalysis | None:
        with self._session_factory() as session:
            model = session.get(DiscoveryAIAnalysisModel, analysis_id)
            return self._to_entity(model) if model else None

    def get_latest_by_scan(self, scan_id: int) -> DiscoveryAIAnalysis | None:
        return self._first(DiscoveryAIAnalysisModel.discovery_scan_id == scan_id)

    def get_latest_by_company(self, company_id: int) -> DiscoveryAIAnalysis | None:
        return self._first(DiscoveryAIAnalysisModel.company_id == company_id)

    def list_by_scan(self, scan_id: int) -> list[DiscoveryAIAnalysis]:
        return self._list(
            select(DiscoveryAIAnalysisModel)
            .where(DiscoveryAIAnalysisModel.discovery_scan_id == scan_id)
            .order_by(
                DiscoveryAIAnalysisModel.created_at.desc(),
                DiscoveryAIAnalysisModel.id.desc(),
            )
        )

    def list_by_company(self, company_id: int) -> list[DiscoveryAIAnalysis]:
        return self._list(
            select(DiscoveryAIAnalysisModel)
            .where(DiscoveryAIAnalysisModel.company_id == company_id)
            .order_by(DiscoveryAIAnalysisModel.created_at.desc())
        )

    def list_recent(self, limit: int = 20) -> list[DiscoveryAIAnalysis]:
        return self._list(
            select(DiscoveryAIAnalysisModel)
            .order_by(DiscoveryAIAnalysisModel.created_at.desc())
            .limit(limit)
        )

    def list_by_status(self, status: str) -> list[DiscoveryAIAnalysis]:
        return self._list(
            select(DiscoveryAIAnalysisModel).where(
                DiscoveryAIAnalysisModel.status == status
            )
        )

    def count(self) -> int:
        with self._session_factory() as session:
            return session.scalar(select(func.count(DiscoveryAIAnalysisModel.id))) or 0

    def delete(self, analysis_id: int) -> bool:
        with self._session_factory() as session, session.begin():
            model = session.get(DiscoveryAIAnalysisModel, analysis_id)
            if not model:
                return False
            session.delete(model)
            return True

    def update_review(
        self, analysis_id: int, status: str, notes: str | None
    ) -> DiscoveryAIAnalysis:
        with self._session_factory() as session, session.begin():
            model = self._required(session, analysis_id)
            model.review_status = status
            model.reviewed_at = utcnow() if status != "Unreviewed" else None
            model.reviewer_notes = (notes or "").strip()[:2000] or None
            session.flush()
            session.refresh(model)
            return self._detach(session, model)

    def dashboard_summary(self) -> dict[str, Any]:
        recent = self.list_recent(5)
        with self._session_factory() as session:
            rows = dict(
                session.execute(
                    select(DiscoveryAIAnalysisModel.status, func.count()).group_by(
                        DiscoveryAIAnalysisModel.status
                    )
                ).all()
            )
        services: dict[str, int] = {}
        for item in self.list_by_status("Completed"):
            for rec in item.recommended_services:
                services[rec["service"]] = services.get(rec["service"], 0) + 1
        return {
            "completed": rows.get("Completed", 0),
            "failed": rows.get("Failed", 0),
            "awaiting_review": sum(
                1
                for x in self.list_by_status("Completed")
                if x.review_status == "Unreviewed"
            ),
            "recent": recent,
            "top_services": sorted(services.items(), key=lambda x: (-x[1], x[0]))[:5],
        }

    def _first(self, criterion: Any) -> DiscoveryAIAnalysis | None:
        rows = self._list(
            select(DiscoveryAIAnalysisModel)
            .where(criterion)
            .order_by(
                DiscoveryAIAnalysisModel.created_at.desc(),
                DiscoveryAIAnalysisModel.id.desc(),
            )
            .limit(1)
        )
        return rows[0] if rows else None

    def _list(self, statement: Any) -> list[DiscoveryAIAnalysis]:
        with self._session_factory() as session:
            return [self._to_entity(x) for x in session.scalars(statement)]

    @staticmethod
    def _required(session: Session, analysis_id: int) -> DiscoveryAIAnalysisModel:
        model = session.get(DiscoveryAIAnalysisModel, analysis_id)
        if model is None:
            raise LookupError("AI analysis not found")
        return model

    def _detach(
        self, session: Session, model: DiscoveryAIAnalysisModel
    ) -> DiscoveryAIAnalysis:
        result = self._to_entity(model)
        session.expunge(model)
        return result

    @staticmethod
    def _to_entity(model: DiscoveryAIAnalysisModel) -> DiscoveryAIAnalysis:
        fixed = {
            "id",
            "discovery_scan_id",
            "company_id",
            "status",
            "review_status",
            "provider",
            "model",
            "prompt_version",
            "schema_version",
            "generated_at",
            "completed_at",
            "error_message",
            "input_snapshot_hash",
            "created_at",
            "updated_at",
            "reviewed_at",
            "reviewer_notes",
        }
        data = {
            c.name: (
                json.loads(
                    getattr(model, c.name)
                    or ("{}" if c.name == "raw_response_metadata" else "[]")
                )
                if c.name in JSON_FIELDS
                else getattr(model, c.name)
            )
            for c in model.__table__.columns
            if c.name not in fixed
        }
        return DiscoveryAIAnalysis(
            **{key: getattr(model, key) for key in fixed}, data=data
        )
