from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from leadpilot.application.crm import CrmService, neutralize_formula


class SalesIntelligenceError(ValueError):
    """Raised for unsafe, invalid, or cross-tenant intelligence operations."""


@dataclass(frozen=True, slots=True)
class IntelligencePage:
    items: tuple[object, ...]
    total: int


DEFAULT_CONFIG: dict[str, object] = {
    "default_forecast_method": "STAGE_WEIGHTED",
    "stale_lead_days": 14,
    "stale_opportunity_days": 21,
    "lead_priority_threshold": 60,
    "opportunity_risk_threshold": 40,
    "high_health_threshold": 80,
    "medium_health_threshold": 60,
    "low_health_threshold": 40,
    "forecast_commit_threshold": 75,
    "forecast_best_case_threshold": 50,
    "default_forecast_horizon_days": 90,
}
RECOMMENDATION_TYPES = {
    "FOLLOW_UP",
    "CALL",
    "EMAIL",
    "MEETING",
    "DEMO",
    "UPDATE_CLOSE_DATE",
    "REVIEW_PRICING",
    "REVIEW_SCOPE",
    "REQUALIFY",
    "ESCALATE",
    "REASSIGN",
    "ADVANCE_STAGE",
    "HOLD",
    "MARK_AT_RISK",
    "CREATE_TASK",
    "REVIEW_PROPOSAL_ENGAGEMENT",
}
PRIORITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}
FORECAST_METHODS = {
    "STAGE_WEIGHTED",
    "MANAGER_COMMIT",
    "BEST_CASE",
    "WORST_CASE",
    "SCENARIO",
}


class SalesIntelligenceRepository(Protocol):
    def get_config(self) -> object | None: ...
    def save_config(self, values: dict[str, object]) -> object: ...
    def entity_snapshot(self, entity: str, entity_id: int) -> dict[str, object]: ...
    def list_entity_snapshots(self, entity: str) -> tuple[dict[str, object], ...]: ...
    def save_score(self, entity: str, values: dict[str, object]) -> object: ...
    def latest_score(self, entity: str, entity_id: int) -> object | None: ...
    def score_history(self, entity: str, entity_id: int) -> tuple[object, ...]: ...
    def create_recommendation(self, values: dict[str, object]) -> object: ...
    def get_recommendation(self, recommendation_id: int) -> object: ...
    def update_recommendation(
        self, recommendation_id: int, values: dict[str, object]
    ) -> object: ...
    def list_recommendations(self, **filters: object) -> IntelligencePage: ...
    def create_task_or_activity(
        self, recommendation: object, entity: str, user_id: int | None
    ) -> object: ...
    def create_forecasts(
        self, forecasts: tuple[dict[str, object], ...]
    ) -> tuple[object, ...]: ...
    def list_forecasts(self) -> tuple[object, ...]: ...
    def create_win_loss(
        self, opportunity_id: int, reason: str, user_id: int | None
    ) -> object: ...
    def team_metrics(self) -> tuple[dict[str, object], ...]: ...


def snapshot_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def lead_priority_score(
    snapshot: dict[str, object], stale_days: int = 14
) -> tuple[int, dict[str, int], tuple[str, ...]]:
    now = datetime.now(UTC)
    last = snapshot.get("last_activity_at") or snapshot.get("last_contacted_at")
    stale = not last or (now - _aware(last)).days >= stale_days
    follow_up = snapshot.get("next_follow_up_at")
    overdue = bool(follow_up and _aware(follow_up) < now)
    breakdown = {
        "qualification": round(int(snapshot.get("score") or 0) * 0.25),
        "recent_activity": 10 if not stale else 0,
        "contact_availability": 10
        if snapshot.get("contact_id") or snapshot.get("email") or snapshot.get("phone")
        else 0,
        "discovery_evidence": 10 if snapshot.get("discovery_completed") else 0,
        "proposal_engagement": min(15, int(snapshot.get("proposal_engagement") or 0)),
        "estimated_value": 10
        if Decimal(str(snapshot.get("estimated_value") or 0)) > 0
        else 0,
        "follow_up_urgency": 10 if overdue else 5 if follow_up else 0,
        "owner_assignment": 5 if snapshot.get("owner_user_id") else 0,
        "source_quality": 5
        if snapshot.get("source") in {"DISCOVERY", "REFERRAL", "WEBSITE"}
        else 2,
    }
    flags = tuple(
        flag
        for flag, active in (
            ("STALE", stale),
            ("FOLLOW_UP_OVERDUE", overdue),
            ("UNASSIGNED", not snapshot.get("owner_user_id")),
            (
                "NO_CONTACT",
                not (
                    snapshot.get("contact_id")
                    or snapshot.get("email")
                    or snapshot.get("phone")
                ),
            ),
        )
        if active
    )
    return min(100, max(0, sum(breakdown.values()))), breakdown, flags


def priority_band(score: int) -> str:
    return (
        "URGENT"
        if score >= 80
        else "HIGH"
        if score >= 60
        else "MEDIUM"
        if score >= 40
        else "LOW"
    )


def opportunity_health_score(
    snapshot: dict[str, object], stale_days: int = 21
) -> tuple[int, dict[str, int], tuple[str, ...]]:
    now = datetime.now(UTC)
    last = snapshot.get("last_activity_at")
    stale = not last or (now - _aware(last)).days >= stale_days
    close_date = snapshot.get("expected_close_date")
    close_passed = bool(close_date and close_date < now.date())
    overdue_tasks = int(snapshot.get("overdue_tasks") or 0)
    breakdown = {
        "recent_activity": 15 if not stale else 0,
        "task_health": 10 if not overdue_tasks else 0,
        "proposal_engagement": min(20, int(snapshot.get("proposal_engagement") or 0)),
        "stage_progression": 15
        if int(snapshot.get("probability_percentage") or 0) >= 30
        else 8,
        "close_date_health": 10 if close_date and not close_passed else 0,
        "contact_readiness": 10 if snapshot.get("primary_contact_id") else 0,
        "next_step_readiness": 10 if snapshot.get("next_step") else 0,
        "owner_assignment": 5 if snapshot.get("owner_user_id") else 0,
        "probability_alignment": 5
        if 0 <= int(snapshot.get("probability_percentage") or 0) <= 100
        else 0,
    }
    flags = tuple(
        flag
        for flag, active in (
            ("STALE", stale),
            ("OVERDUE_TASKS", overdue_tasks > 0),
            ("CLOSE_DATE_PASSED", close_passed),
            ("NO_PRIMARY_CONTACT", not snapshot.get("primary_contact_id")),
            ("NO_NEXT_STEP", not snapshot.get("next_step")),
            ("UNASSIGNED", not snapshot.get("owner_user_id")),
        )
        if active
    )
    return min(100, max(0, sum(breakdown.values()))), breakdown, flags


def health_band(score: int) -> str:
    return (
        "HEALTHY"
        if score >= 80
        else "WATCH"
        if score >= 60
        else "AT_RISK"
        if score >= 40
        else "CRITICAL"
    )


class SalesIntelligenceService:
    def __init__(
        self,
        repository: SalesIntelligenceRepository,
        crm: CrmService,
        user_id: int | None = None,
        authorize_read: object = None,
        authorize_calculate: object = None,
        authorize_manage: object = None,
        authorize_admin: object = None,
        audit: object = None,
    ) -> None:
        self.repo, self.crm, self.user_id = repository, crm, user_id
        self.read, self.calculate, self.manage, self.admin, self.audit = (
            authorize_read,
            authorize_calculate,
            authorize_manage,
            authorize_admin,
            audit,
        )

    def get_config(self) -> object:
        self._auth(self.read)
        return self.repo.get_config() or DEFAULT_CONFIG.copy()

    def update_config(self, **values: object) -> object:
        self._auth(self.admin)
        for key, value in values.items():
            if key.endswith(("threshold", "weight")) and not 0 <= int(value) <= 100:
                raise SalesIntelligenceError(f"{key} must be between 0 and 100.")
            if key.endswith("days") and not 0 <= int(value) <= 3650:
                raise SalesIntelligenceError(f"{key} is out of range.")
        result = self.repo.save_config(
            {
                **values,
                "updated_by_user_id": self.user_id,
                "created_by_user_id": self.user_id,
            }
        )
        self._audit("SALES_INTELLIGENCE_CONFIG_UPDATED", result)
        return result

    def calculate_lead_priority(self, lead_id: int) -> object:
        self._auth(self.calculate)
        config = self.get_config()
        source = self.repo.entity_snapshot("LEAD", lead_id)
        score, breakdown, flags = lead_priority_score(
            source, int(_get(config, "stale_lead_days", 14))
        )
        result = self.repo.save_score(
            "LEAD",
            {
                "lead_id": lead_id,
                "score": score,
                "priority_band": priority_band(score),
                "score_breakdown_json": breakdown,
                "risk_flags_json": flags,
                "recommended_follow_up_at": datetime.now(UTC) + timedelta(days=1)
                if flags
                else None,
                "source_snapshot_hash": snapshot_hash(source),
                "calculated_at": datetime.now(UTC),
                "calculated_by_user_id": self.user_id,
            },
        )
        self._audit("LEAD_PRIORITY_CALCULATED", result)
        return result

    def calculate_health(self, opportunity_id: int) -> object:
        self._auth(self.calculate)
        config = self.get_config()
        source = self.repo.entity_snapshot("OPPORTUNITY", opportunity_id)
        score, breakdown, flags = opportunity_health_score(
            source, int(_get(config, "stale_opportunity_days", 21))
        )
        band = health_band(score)
        result = self.repo.save_score(
            "OPPORTUNITY",
            {
                "opportunity_id": opportunity_id,
                "health_score": score,
                "health_band": band,
                "risk_level": "CRITICAL"
                if band == "CRITICAL"
                else "HIGH"
                if band == "AT_RISK"
                else "MEDIUM"
                if band == "WATCH"
                else "LOW",
                "score_breakdown_json": breakdown,
                "risk_flags_json": flags,
                "recommended_action": "Review next steps and follow-up."
                if flags
                else None,
                "source_snapshot_hash": snapshot_hash(source),
                "calculated_at": datetime.now(UTC),
                "calculated_by_user_id": self.user_id,
            },
        )
        self._audit("OPPORTUNITY_HEALTH_CALCULATED", result)
        return result

    def calculate_all_lead_priorities(self) -> tuple[object, ...]:
        return tuple(
            self.calculate_lead_priority(int(x["id"]))
            for x in self.repo.list_entity_snapshots("LEAD")
        )

    def calculate_all_health_scores(self) -> tuple[object, ...]:
        return tuple(
            self.calculate_health(int(x["id"]))
            for x in self.repo.list_entity_snapshots("OPPORTUNITY")
        )

    def get_latest_score(self, entity: str, entity_id: int) -> object | None:
        self._auth(self.read)
        return self.repo.latest_score(entity.upper(), entity_id)

    def get_score_history(self, entity: str, entity_id: int) -> tuple[object, ...]:
        self._auth(self.read)
        return self.repo.score_history(entity.upper(), entity_id)

    def generate_recommendations(
        self, entity: str, entity_id: int
    ) -> tuple[object, ...]:
        self._auth(self.calculate)
        entity = entity.upper()
        source = self.repo.entity_snapshot(entity, entity_id)
        candidates: list[tuple[str, str, str]] = []
        if entity == "LEAD":
            latest = self.calculate_lead_priority(entity_id)
            flags = set(latest.risk_flags_json)
            if "FOLLOW_UP_OVERDUE" in flags or "STALE" in flags:
                candidates.append(("FOLLOW_UP", "HIGH", "Follow up with this lead"))
            if "UNASSIGNED" in flags:
                candidates.append(("REASSIGN", "MEDIUM", "Review lead ownership"))
        else:
            latest = self.calculate_health(entity_id)
            flags = set(latest.risk_flags_json)
            if "CLOSE_DATE_PASSED" in flags:
                candidates.append(
                    ("UPDATE_CLOSE_DATE", "HIGH", "Review the expected close date")
                )
            if flags:
                candidates.append(
                    ("CREATE_TASK", "HIGH", "Create an opportunity review task")
                )
        digest = snapshot_hash(source)
        results = []
        for kind, priority, title in candidates:
            results.append(
                self.repo.create_recommendation(
                    {
                        "entity_type": entity,
                        "entity_id": entity_id,
                        "recommendation_type": kind,
                        "status": "PENDING_REVIEW",
                        "priority": priority,
                        "title": title,
                        "description": "Review CRM evidence and confirm the next action.",
                        "reasoning_json": sorted(flags),
                        "source_references_json": [
                            {
                                "source_type": entity,
                                "source_id": source.get("safe_reference"),
                            }
                        ],
                        "source_snapshot_hash": digest,
                        "created_by_user_id": self.user_id,
                    }
                )
            )
        return tuple(results)

    def record_ai_recommendations(
        self, entity: str, entity_id: int, payload: dict[str, object], ai_run_id: int
    ) -> tuple[object, ...]:
        """Validate structured AI output and persist reviewable suggestions only."""
        self._auth(self.calculate)
        entity = entity.upper()
        source = self.repo.entity_snapshot(entity, entity_id)
        safe_reference = source.get("safe_reference")
        raw_items = payload.get("recommendations", [])
        if not isinstance(raw_items, list) or len(raw_items) > 20:
            raise SalesIntelligenceError("AI recommendation output is invalid.")
        forbidden = {
            "amount",
            "probability",
            "probability_percentage",
            "stage_id",
            "owner_user_id",
            "expected_close_date",
            "send_email",
        }
        output = []
        for raw in raw_items:
            if not isinstance(raw, dict) or forbidden & raw.keys():
                raise SalesIntelligenceError(
                    "AI output requested an unsupported mutation."
                )
            kind, priority = raw.get("recommendation_type"), raw.get("priority")
            title, description = (
                str(raw.get("title", "")),
                str(raw.get("description", "")),
            )
            if kind not in RECOMMENDATION_TYPES or priority not in PRIORITIES:
                raise SalesIntelligenceError("AI recommendation type is invalid.")
            if not title.strip() or len(title) > 300 or len(description) > 2000:
                raise SalesIntelligenceError("AI recommendation text is invalid.")
            if any(
                token in f"{title} {description}"
                for token in ("<script", "javascript:")
            ):
                raise SalesIntelligenceError("AI recommendation text is unsafe.")
            references = raw.get("source_references", [])
            if not isinstance(references, list) or any(
                not isinstance(ref, dict) or ref.get("source_id") != safe_reference
                for ref in references
            ):
                raise SalesIntelligenceError("AI source reference is invalid.")
            output.append(
                self.repo.create_recommendation(
                    {
                        "entity_type": entity,
                        "entity_id": entity_id,
                        "recommendation_type": kind,
                        "status": "PENDING_REVIEW",
                        "priority": priority,
                        "title": title.strip(),
                        "description": description.strip(),
                        "reasoning_json": raw.get("reasoning", []),
                        "source_references_json": references,
                        "source_snapshot_hash": snapshot_hash(source),
                        "ai_run_id": ai_run_id,
                        "created_by_user_id": self.user_id,
                    }
                )
            )
        return tuple(output)

    def approve_recommendation(self, recommendation_id: int) -> object:
        return self._review(
            recommendation_id, "APPROVED", "SALES_RECOMMENDATION_APPROVED"
        )

    def reject_recommendation(self, recommendation_id: int) -> object:
        return self._review(
            recommendation_id, "REJECTED", "SALES_RECOMMENDATION_REJECTED"
        )

    def bulk_approve(self, recommendation_ids: tuple[int, ...]) -> tuple[object, ...]:
        return tuple(self.approve_recommendation(item) for item in recommendation_ids)

    def bulk_reject(self, recommendation_ids: tuple[int, ...]) -> tuple[object, ...]:
        return tuple(self.reject_recommendation(item) for item in recommendation_ids)

    def supersede_pending(self, entity: str, entity_id: int) -> tuple[object, ...]:
        self._auth(self.manage)
        page = self.repo.list_recommendations(
            entity_type=entity.upper(), status="PENDING_REVIEW", page_size=500
        )
        results = []
        for item in page.items:
            if item.entity_id == entity_id:
                results.append(
                    self.repo.update_recommendation(
                        item.id,
                        {"status": "SUPERSEDED", "superseded_at": datetime.now(UTC)},
                    )
                )
        return tuple(results)

    def get_recommendation_history(
        self, entity: str, entity_id: int
    ) -> tuple[object, ...]:
        self._auth(self.read)
        return tuple(
            item
            for item in self.repo.list_recommendations(
                entity_type=entity.upper(), page_size=500
            ).items
            if item.entity_id == entity_id
        )

    def apply_recommendation(self, recommendation_id: int) -> object:
        self._auth(self.manage)
        item = self.repo.get_recommendation(recommendation_id)
        if item.status != "APPROVED":
            raise SalesIntelligenceError(
                "Recommendation must be approved before it is applied."
            )
        target = (
            "activity"
            if item.recommendation_type in {"CALL", "MEETING", "EMAIL"}
            else "task"
        )
        created = self.repo.create_task_or_activity(item, target, self.user_id)
        values = {
            "status": "APPLIED",
            "applied_activity_id"
            if target == "activity"
            else "applied_task_id": created.id,
        }
        result = self.repo.update_recommendation(recommendation_id, values)
        self._audit("SALES_RECOMMENDATION_APPLIED", result)
        return result

    def list_recommendations(self, **filters: object) -> IntelligencePage:
        self._auth(self.read)
        return self.repo.list_recommendations(**filters)

    def generate_forecast(
        self,
        period_start: date,
        period_end: date,
        method: str = "STAGE_WEIGHTED",
        scenario: dict[str, object] | None = None,
    ) -> tuple[object, ...]:
        self._auth(self.manage)
        if method not in FORECAST_METHODS or period_start > period_end:
            raise SalesIntelligenceError("Forecast parameters are invalid.")
        config = self.get_config()
        opportunities = self.repo.list_entity_snapshots("OPPORTUNITY")
        adjustment = Decimal(str((scenario or {}).get("probability_adjustment", 0)))
        grouped: dict[str, list[dict[str, object]]] = {}
        for item in opportunities:
            close = item.get("expected_close_date")
            if close and not period_start <= close <= period_end:
                continue
            grouped.setdefault(str(item["currency"]), []).append(item)
        records = []
        for currency, items in grouped.items():
            open_amount = sum(
                (Decimal(str(x["amount"])) for x in items if x["status"] == "OPEN"),
                Decimal(),
            )
            weighted = sum(
                (
                    Decimal(str(x["amount"]))
                    * max(
                        Decimal(),
                        min(
                            Decimal(100),
                            Decimal(str(x["probability_percentage"])) + adjustment,
                        ),
                    )
                    / 100
                    for x in items
                    if x["status"] == "OPEN"
                ),
                Decimal(),
            )
            commit = sum(
                (
                    Decimal(str(x["amount"]))
                    for x in items
                    if x["status"] == "OPEN"
                    and int(x["probability_percentage"])
                    >= int(_get(config, "forecast_commit_threshold", 75))
                ),
                Decimal(),
            )
            best = sum(
                (
                    Decimal(str(x["amount"]))
                    for x in items
                    if x["status"] == "OPEN"
                    and int(x["probability_percentage"])
                    >= int(_get(config, "forecast_best_case_threshold", 50))
                ),
                Decimal(),
            )
            won = sum(
                (Decimal(str(x["amount"])) for x in items if x["status"] == "WON"),
                Decimal(),
            )
            lost = sum(
                (Decimal(str(x["amount"])) for x in items if x["status"] == "LOST"),
                Decimal(),
            )
            records.append(
                {
                    "forecast_date": datetime.now(UTC).date(),
                    "period_start": period_start,
                    "period_end": period_end,
                    "forecast_method": method,
                    "currency": currency,
                    "open_pipeline_amount": open_amount,
                    "weighted_pipeline_amount": weighted.quantize(
                        Decimal("0.01"), ROUND_HALF_UP
                    ),
                    "commit_amount": commit,
                    "best_case_amount": best,
                    "worst_case_amount": won + commit,
                    "won_amount": won,
                    "lost_amount": lost,
                    "scenario_json": scenario or {},
                    "source_snapshot_hash": snapshot_hash(items),
                    "generated_by_user_id": self.user_id,
                    "snapshots": items,
                }
            )
        result = self.repo.create_forecasts(tuple(records))
        for item in result:
            self._audit("REVENUE_FORECAST_GENERATED", item)
        return result

    def pipeline_risks(self) -> tuple[dict[str, object], ...]:
        self._auth(self.read)
        rows = self.repo.list_entity_snapshots("OPPORTUNITY")
        total = sum(
            (Decimal(str(x["amount"])) for x in rows if x["status"] == "OPEN"),
            Decimal(),
        )
        risks = []
        for row in rows:
            amount = Decimal(str(row["amount"]))
            flags = opportunity_health_score(row)[2]
            if total and amount / total >= Decimal("0.5"):
                risks.append(
                    {
                        "risk_type": "OPPORTUNITY_CONCENTRATION",
                        "severity": "HIGH",
                        "amount_affected": amount,
                        "opportunities_affected": 1,
                        "explanation": "At least half of open pipeline is concentrated in one opportunity.",
                    }
                )
            if flags:
                risks.append(
                    {
                        "risk_type": "STALE_OR_INCOMPLETE",
                        "severity": "HIGH"
                        if "CLOSE_DATE_PASSED" in flags
                        else "MEDIUM",
                        "amount_affected": amount,
                        "opportunities_affected": 1,
                        "explanation": ", ".join(flags),
                    }
                )
        return tuple(risks)

    def get_risk_summary(self) -> dict[str, object]:
        risks = self.pipeline_risks()
        return {
            "total": len(risks),
            "high": sum(item["severity"] in {"HIGH", "CRITICAL"} for item in risks),
            "amount_affected": sum(
                (Decimal(str(item["amount_affected"])) for item in risks), Decimal()
            ),
        }

    def list_forecasts(self) -> tuple[object, ...]:
        self._auth(self.read)
        return self.repo.list_forecasts()

    def get_forecast(self, forecast_id: int) -> object:
        self._auth(self.read)
        result = next(
            (item for item in self.repo.list_forecasts() if item.id == forecast_id),
            None,
        )
        if result is None:
            raise SalesIntelligenceError("Forecast is unavailable.")
        return result

    def compare_forecasts(self, first_id: int, second_id: int) -> dict[str, Decimal]:
        first, second = self.get_forecast(first_id), self.get_forecast(second_id)
        if first.currency != second.currency:
            raise SalesIntelligenceError("Forecast currencies cannot be combined.")
        return {
            field: Decimal(str(getattr(second, field)))
            - Decimal(str(getattr(first, field)))
            for field in (
                "weighted_pipeline_amount",
                "commit_amount",
                "best_case_amount",
                "worst_case_amount",
            )
        }

    @staticmethod
    def build_scenario(
        probability_adjustment: int = 0,
        risk_bands: tuple[str, ...] = (),
    ) -> dict[str, object]:
        if not -100 <= probability_adjustment <= 100:
            raise SalesIntelligenceError("Scenario adjustment is out of range.")
        allowed = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        if not set(risk_bands) <= allowed:
            raise SalesIntelligenceError("Scenario risk band is invalid.")
        return {
            "probability_adjustment": probability_adjustment,
            "risk_bands": risk_bands,
        }

    def analyze_opportunity(self, opportunity_id: int, reason: str) -> object:
        self._auth(self.manage)
        result = self.repo.create_win_loss(opportunity_id, reason.strip(), self.user_id)
        self._audit("WIN_LOSS_ANALYSIS_CREATED", result)
        return result

    def team_metrics(self) -> tuple[dict[str, object], ...]:
        self._auth(self.manage)
        return self.repo.team_metrics()

    def dashboard(self) -> dict[str, object]:
        self._auth(self.read)
        leads = self.calculate_all_lead_priorities() if self.calculate else ()
        health = self.calculate_all_health_scores() if self.calculate else ()
        return {
            "high_priority_leads": sum(
                x.priority_band in {"HIGH", "URGENT"} for x in leads
            ),
            "urgent_leads": sum(x.priority_band == "URGENT" for x in leads),
            "healthy_opportunities": sum(x.health_band == "HEALTHY" for x in health),
            "at_risk_opportunities": sum(
                x.health_band in {"AT_RISK", "CRITICAL"} for x in health
            ),
            "recommendations": self.list_recommendations(status="PENDING_REVIEW").total,
            "pipeline_risks": len(self.pipeline_risks()),
        }

    def export_csv(self, rows: tuple[dict[str, object], ...]) -> bytes:
        self._auth(self.read)
        if not rows:
            return b""
        safe = [
            {
                k: neutralize_formula(v)
                for k, v in row.items()
                if not k.endswith("_id") and k not in {"notes", "reasoning_json"}
            }
            for row in rows
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(safe[0]))
        writer.writeheader()
        writer.writerows(safe)
        self._audit("SALES_INTELLIGENCE_EXPORTED", None)
        return output.getvalue().encode()

    def _review(self, recommendation_id: int, status: str, event: str) -> object:
        self._auth(self.manage)
        item = self.repo.get_recommendation(recommendation_id)
        if item.status != "PENDING_REVIEW":
            raise SalesIntelligenceError(
                "Only pending recommendations may be reviewed."
            )
        result = self.repo.update_recommendation(
            recommendation_id,
            {
                "status": status,
                "reviewed_by_user_id": self.user_id,
                "reviewed_at": datetime.now(UTC),
            },
        )
        self._audit(event, result)
        return result

    @staticmethod
    def _auth(callback: object) -> None:
        if callable(callback):
            callback()

    def _audit(self, action: str, entity: object | None) -> None:
        if callable(self.audit):
            self.audit(action, "sales_intelligence", getattr(entity, "id", None))


def _aware(value: object) -> datetime:
    result = (
        value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    )
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result


def _get(value: object, key: str, default: object) -> object:
    return (
        value.get(key, default)
        if isinstance(value, dict)
        else getattr(value, key, default)
    )
