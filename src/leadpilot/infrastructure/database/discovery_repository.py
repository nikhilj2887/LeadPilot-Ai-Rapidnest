from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from leadpilot.application.discovery import (
    DISCOVERY_STATUSES,
    DiscoveryScan,
    DiscoverySummary,
    utcnow,
)
from leadpilot.infrastructure.database.models import DiscoveryScanModel

JSON_FIELDS = {
    "detected_technologies",
    "detected_emails",
    "detected_phone_numbers",
    "detected_social_links",
    "score_details",
    "findings",
    "recommendations",
}
RESULT_FIELDS = {column.name for column in DiscoveryScanModel.__table__.columns} - {
    "id",
    "company_id",
    "website_url",
    "status",
    "started_at",
    "completed_at",
    "error_message",
    "created_at",
    "updated_at",
}


class DiscoveryRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def create(self, company_id: int, website_url: str) -> DiscoveryScan:
        with self._session_factory() as session, session.begin():
            model = DiscoveryScanModel(company_id=company_id, website_url=website_url)
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._detach(session, model)

    def update_status(self, scan_id: int, status: str) -> DiscoveryScan:
        if status not in DISCOVERY_STATUSES:
            raise ValueError("Invalid discovery status")
        with self._session_factory() as session, session.begin():
            model = self._required(session, scan_id)
            allowed = {
                "Pending": {"Running", "Failed"},
                "Running": {"Completed", "Failed"},
                "Completed": set(),
                "Failed": set(),
            }
            if status != model.status and status not in allowed[model.status]:
                raise ValueError(
                    f"Invalid discovery transition: {model.status} to {status}"
                )
            model.status = status
            if status == "Running":
                model.started_at = utcnow()
            session.flush()
            session.refresh(model)
            return self._detach(session, model)

    def save_completed_result(
        self, scan_id: int, values: dict[str, Any]
    ) -> DiscoveryScan:
        with self._session_factory() as session, session.begin():
            model = self._required(session, scan_id)
            if model.status != "Running":
                raise ValueError("Only a running scan can be completed")
            for key, value in values.items():
                if key in RESULT_FIELDS:
                    setattr(
                        model, key, json.dumps(value) if key in JSON_FIELDS else value
                    )
            model.status = "Completed"
            model.completed_at = utcnow()
            model.error_message = None
            session.flush()
            session.refresh(model)
            return self._detach(session, model)

    def save_failed_result(self, scan_id: int, message: str) -> DiscoveryScan:
        safe = message.strip()[:1000] or "The website scan failed."
        with self._session_factory() as session, session.begin():
            model = self._required(session, scan_id)
            if model.status not in {"Pending", "Running"}:
                raise ValueError("A finished scan cannot be failed")
            model.status = "Failed"
            model.error_message = safe
            model.completed_at = utcnow()
            session.flush()
            session.refresh(model)
            return self._detach(session, model)

    def get_by_id(self, scan_id: int) -> DiscoveryScan | None:
        with self._session_factory() as session:
            model = session.get(DiscoveryScanModel, scan_id)
            return self._to_scan(model) if model else None

    def get_latest_by_company(self, company_id: int) -> DiscoveryScan | None:
        scans = self._list(
            select(DiscoveryScanModel)
            .where(DiscoveryScanModel.company_id == company_id)
            .order_by(
                DiscoveryScanModel.created_at.desc(), DiscoveryScanModel.id.desc()
            )
            .limit(1)
        )
        return scans[0] if scans else None

    def list_by_company(self, company_id: int) -> list[DiscoveryScan]:
        return self._list(
            select(DiscoveryScanModel)
            .where(DiscoveryScanModel.company_id == company_id)
            .order_by(DiscoveryScanModel.created_at.desc())
        )

    def list_recent(self, limit: int = 50) -> list[DiscoveryScan]:
        return self._list(
            select(DiscoveryScanModel)
            .order_by(
                DiscoveryScanModel.created_at.desc(), DiscoveryScanModel.id.desc()
            )
            .limit(limit)
        )

    def list_by_status(self, status: str) -> list[DiscoveryScan]:
        return self._list(
            select(DiscoveryScanModel).where(DiscoveryScanModel.status == status)
        )

    def count(self) -> int:
        with self._session_factory() as session:
            return session.scalar(select(func.count(DiscoveryScanModel.id))) or 0

    def count_by_status(self) -> dict[str, int]:
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    DiscoveryScanModel.status, func.count(DiscoveryScanModel.id)
                ).group_by(DiscoveryScanModel.status)
            )
            return dict(rows)

    def delete(self, scan_id: int) -> bool:
        with self._session_factory() as session, session.begin():
            model = session.get(DiscoveryScanModel, scan_id)
            if model is None:
                return False
            session.delete(model)
            return True

    def summary(self) -> DiscoverySummary:
        recent = self.list_recent(5)
        with self._session_factory() as session:
            total, completed, failed, avg_lead, high, avg_auto = session.execute(
                select(
                    func.count(DiscoveryScanModel.id),
                    func.sum(
                        func.cast(
                            DiscoveryScanModel.status == "Completed",
                            type_=DiscoveryScanModel.id.type,
                        )
                    ),
                    func.sum(
                        func.cast(
                            DiscoveryScanModel.status == "Failed",
                            type_=DiscoveryScanModel.id.type,
                        )
                    ),
                    func.avg(DiscoveryScanModel.lead_priority_score).filter(
                        DiscoveryScanModel.status == "Completed"
                    ),
                    func.sum(
                        func.cast(
                            DiscoveryScanModel.lead_priority_score >= 61,
                            type_=DiscoveryScanModel.id.type,
                        )
                    ),
                    func.avg(DiscoveryScanModel.automation_potential_score).filter(
                        DiscoveryScanModel.status == "Completed"
                    ),
                )
            ).one()
        return DiscoverySummary(
            total=total or 0,
            completed=completed or 0,
            failed=failed or 0,
            average_lead_priority=round(avg_lead or 0, 1),
            high_priority=high or 0,
            average_automation_potential=round(avg_auto or 0, 1),
            recent=recent,
        )

    def _list(self, statement: Any) -> list[DiscoveryScan]:
        with self._session_factory() as session:
            return [self._to_scan(model) for model in session.scalars(statement)]

    @staticmethod
    def _required(session: Session, scan_id: int) -> DiscoveryScanModel:
        model = session.get(DiscoveryScanModel, scan_id)
        if model is None:
            raise LookupError(f"Discovery scan {scan_id} was not found")
        return model

    def _detach(self, session: Session, model: DiscoveryScanModel) -> DiscoveryScan:
        result = self._to_scan(model)
        session.expunge(model)
        return result

    @staticmethod
    def _to_scan(model: DiscoveryScanModel) -> DiscoveryScan:
        excluded = {
            "id",
            "company_id",
            "website_url",
            "status",
            "started_at",
            "completed_at",
            "error_message",
            "created_at",
            "updated_at",
        }
        data = {
            column.name: (
                json.loads(
                    getattr(model, column.name)
                    or ("{}" if column.name == "score_details" else "[]")
                )
                if column.name in JSON_FIELDS
                else getattr(model, column.name)
            )
            for column in model.__table__.columns
            if column.name in RESULT_FIELDS or column.name in excluded
        }
        for key in excluded:
            data.pop(key, None)
        return DiscoveryScan(
            id=model.id,
            company_id=model.company_id,
            website_url=model.website_url,
            status=model.status,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            data=data,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
