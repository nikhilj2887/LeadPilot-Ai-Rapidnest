from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlparse


class CrmError(ValueError):
    """Raised when a CRM operation violates a tenant or lifecycle rule."""


class LeadStatus(StrEnum):
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    CONTACTED = "CONTACTED"
    NURTURING = "NURTURING"
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    CONVERTED = "CONVERTED"
    ARCHIVED = "ARCHIVED"


LEAD_TRANSITIONS = {
    "NEW": {"ASSIGNED", "CONTACTED", "DISQUALIFIED", "ARCHIVED"},
    "ASSIGNED": {"CONTACTED", "DISQUALIFIED", "ARCHIVED"},
    "CONTACTED": {"NURTURING", "QUALIFIED", "DISQUALIFIED"},
    "NURTURING": {"CONTACTED", "QUALIFIED", "DISQUALIFIED"},
    "QUALIFIED": {"CONVERTED", "NURTURING", "DISQUALIFIED"},
    "DISQUALIFIED": {"NEW", "ARCHIVED"},
    "ARCHIVED": {"NEW"},
    "CONVERTED": set(),
}


@dataclass(frozen=True, slots=True)
class Page:
    items: tuple[object, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class ImportPreview:
    valid_rows: tuple[dict[str, str], ...]
    errors: tuple[str, ...]
    duplicates: tuple[int, ...]


class CrmRepository(Protocol):
    def create(self, entity: str, values: dict[str, object]) -> object: ...
    def update(
        self, entity: str, entity_id: int, values: dict[str, object]
    ) -> object: ...
    def get(self, entity: str, entity_id: int) -> object | None: ...
    def list(
        self,
        entity: str,
        query: str = "",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Page: ...
    def next_number(self, entity: str, prefix: str) -> str: ...
    def ensure_company(self, company_id: int) -> None: ...
    def ensure_contact(
        self, contact_id: int, company_id: int | None = None
    ) -> None: ...
    def ensure_user(self, user_id: int) -> None: ...
    def default_stage(self) -> object: ...
    def move_stage(
        self,
        opportunity_id: int,
        stage_id: int,
        user_id: int | None,
        reason: str | None,
    ) -> object: ...
    def convert(
        self, lead_id: int, opportunity: dict[str, object], user_id: int | None
    ) -> object: ...
    def link_proposal(self, opportunity_id: int, proposal_id: int) -> None: ...
    def timeline(
        self, entity: str, entity_id: int, limit: int, offset: int
    ) -> tuple[object, ...]: ...
    def metrics(self) -> dict[str, object]: ...
    def search(self, query: str, limit: int) -> dict[str, tuple[object, ...]]: ...


def score_lead(values: dict[str, object]) -> tuple[int, dict[str, int]]:
    breakdown = {
        "profile": 10 if values.get("industry") and values.get("country") else 0,
        "website": 10 if _valid_url(str(values.get("website") or "")) else 0,
        "industry_fit": 15 if values.get("industry") else 0,
        "country_fit": 10 if values.get("country") else 0,
        "company_size": 10 if values.get("company_size") else 0,
        "contact": 15
        if values.get("contact_id") or values.get("email") or values.get("phone")
        else 0,
        "discovery": 10 if values.get("discovery_completed") else 0,
        "automation": 10 if int(values.get("automation_score") or 0) >= 70 else 0,
        "lead_priority": 10 if int(values.get("lead_priority_score") or 0) >= 70 else 0,
    }
    return min(100, sum(breakdown.values())), breakdown


def qualification_band(score: int) -> str:
    if score < 40:
        return "NOT_QUALIFIED"
    if score < 60:
        return "MARKETING_QUALIFIED"
    return "SALES_QUALIFIED"


def neutralize_formula(value: object) -> str:
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


class CrmService:
    def __init__(
        self,
        repository: CrmRepository,
        user_id: int | None,
        authorize_read: object = None,
        authorize_write: object = None,
        authorize_manage: object = None,
        audit: object = None,
    ) -> None:
        self.repo, self.user_id = repository, user_id
        self.read, self.write, self.manage, self.audit = (
            authorize_read,
            authorize_write,
            authorize_manage,
            audit,
        )

    def create_contact(
        self, company_id: int, first_name: str, last_name: str, **values: object
    ) -> object:
        self._write()
        self.repo.ensure_company(company_id)
        email = str(values.get("email") or "").strip().casefold() or None
        result = self.repo.create(
            "contact",
            {
                **values,
                "company_id": company_id,
                "first_name": self._required(first_name),
                "last_name": self._required(last_name),
                "email": email,
                "status": "ACTIVE",
                "created_by_user_id": self.user_id,
            },
        )
        self._audit("CONTACT_CREATED", result)
        return result

    def set_primary_contact(self, contact_id: int) -> object:
        self._write()
        return self.repo.update(
            "contact",
            contact_id,
            {"is_primary": True, "updated_by_user_id": self.user_id},
        )

    def archive_contact(self, contact_id: int) -> object:
        return self._status("contact", contact_id, "ARCHIVED", "CONTACT_ARCHIVED")

    def restore_contact(self, contact_id: int) -> object:
        return self._status("contact", contact_id, "ACTIVE", "CONTACT_UPDATED")

    def create_lead(
        self,
        title: str,
        *,
        company_id: int | None = None,
        contact_id: int | None = None,
        source: str = "MANUAL",
        **values: object,
    ) -> object:
        self._write()
        if company_id:
            self.repo.ensure_company(company_id)
        if contact_id:
            self.repo.ensure_contact(contact_id, company_id)
        score, breakdown = score_lead(
            {**values, "company_id": company_id, "contact_id": contact_id}
        )
        result = self.repo.create(
            "lead",
            {
                **values,
                "company_id": company_id,
                "contact_id": contact_id,
                "lead_number": self.repo.next_number("lead", "LEAD"),
                "title": self._required(title),
                "source": source,
                "status": "NEW",
                "qualification_status": "UNASSESSED",
                "priority": values.get("priority", "MEDIUM"),
                "score": score,
                "score_breakdown_json": breakdown,
                "created_by_user_id": self.user_id,
            },
        )
        self._audit(
            "LEAD_CREATED_FROM_DISCOVERY" if source == "DISCOVERY" else "LEAD_CREATED",
            result,
        )
        return result

    def transition_lead(
        self, lead_id: int, status: str, reason: str | None = None
    ) -> object:
        self._write()
        lead = self._get("lead", lead_id)
        if status not in LEAD_TRANSITIONS.get(str(lead.status), set()):
            raise CrmError("Invalid lead status transition.")
        if status == "DISQUALIFIED" and not (reason or "").strip():
            raise CrmError("Disqualification reason is required.")
        result = self.repo.update(
            "lead",
            lead_id,
            {
                "status": status,
                "disqualification_reason": reason if status == "DISQUALIFIED" else None,
                "qualification_status": "NOT_QUALIFIED"
                if status == "DISQUALIFIED"
                else lead.qualification_status,
                "updated_by_user_id": self.user_id,
            },
        )
        self._audit(
            "LEAD_DISQUALIFIED"
            if status == "DISQUALIFIED"
            else "LEAD_QUALIFIED"
            if status == "QUALIFIED"
            else "LEAD_UPDATED",
            result,
        )
        return result

    def assign_lead(
        self, lead_id: int, owner_user_id: int, method: str = "MANUAL"
    ) -> object:
        self._manage()
        self.repo.ensure_user(owner_user_id)
        result = self.repo.update(
            "lead",
            lead_id,
            {
                "owner_user_id": owner_user_id,
                "assigned_at": datetime.now(UTC),
                "status": "ASSIGNED",
                "assignment_method": method,
            },
        )
        self._audit("LEAD_ASSIGNED", result)
        return result

    def convert_lead_to_opportunity(
        self, lead_id: int, name: str, amount: Decimal, currency: str = "INR"
    ) -> object:
        self._manage()
        lead = self._get("lead", lead_id)
        if lead.status != "QUALIFIED" or not lead.company_id:
            raise CrmError("Lead must be qualified and linked to a company.")
        if lead.converted_opportunity_id:
            raise CrmError("Lead has already been converted.")
        stage = self.repo.default_stage()
        probability = int(stage.probability_percentage)
        result = self.repo.convert(
            lead_id,
            {
                "company_id": lead.company_id,
                "primary_contact_id": lead.contact_id,
                "source_lead_id": lead.id,
                "stage_id": stage.id,
                "opportunity_number": self.repo.next_number("opportunity", "OPP"),
                "name": self._required(name),
                "amount": self._money(amount),
                "currency": self._currency(currency),
                "probability_percentage": probability,
                "weighted_amount": (
                    self._money(amount) * Decimal(probability) / 100
                ).quantize(Decimal("0.01"), ROUND_HALF_UP),
                "status": "OPEN",
                "owner_user_id": lead.owner_user_id,
                "created_by_user_id": self.user_id,
            },
            self.user_id,
        )
        self._audit("LEAD_CONVERTED", lead)
        self._audit("OPPORTUNITY_CREATED", result)
        return result

    def create_opportunity(
        self,
        company_id: int,
        name: str,
        amount: Decimal,
        currency: str = "INR",
        **values: object,
    ) -> object:
        self._write()
        self.repo.ensure_company(company_id)
        stage = self.repo.default_stage()
        probability = int(
            values.get("probability_percentage", stage.probability_percentage)
        )
        result = self.repo.create(
            "opportunity",
            {
                **values,
                "company_id": company_id,
                "stage_id": stage.id,
                "opportunity_number": self.repo.next_number("opportunity", "OPP"),
                "name": self._required(name),
                "amount": self._money(amount),
                "currency": self._currency(currency),
                "probability_percentage": probability,
                "weighted_amount": (
                    self._money(amount) * Decimal(probability) / 100
                ).quantize(Decimal("0.01")),
                "status": "OPEN",
                "created_by_user_id": self.user_id,
            },
        )
        self._audit("OPPORTUNITY_CREATED", result)
        return result

    def move_opportunity(
        self, opportunity_id: int, stage_id: int, reason: str | None = None
    ) -> object:
        self._manage()
        result = self.repo.move_stage(opportunity_id, stage_id, self.user_id, reason)
        self._audit("OPPORTUNITY_STAGE_CHANGED", result)
        return result

    def mark_opportunity(self, opportunity_id: int, won: bool, reason: str) -> object:
        self._manage()
        if not reason.strip():
            raise CrmError("A win or loss reason is required.")
        opportunity = self._get("opportunity", opportunity_id)
        result = self.repo.update(
            "opportunity",
            opportunity_id,
            {
                "status": "WON" if won else "LOST",
                "probability_percentage": 100 if won else 0,
                "weighted_amount": opportunity.amount if won else Decimal(0),
                "actual_close_date": datetime.now(UTC).date(),
                "win_reason" if won else "loss_reason": reason,
            },
        )
        self._audit("OPPORTUNITY_WON" if won else "OPPORTUNITY_LOST", result)
        return result

    def link_proposal(self, opportunity_id: int, proposal_id: int) -> None:
        self._manage()
        self.repo.link_proposal(opportunity_id, proposal_id)

    def create_related(
        self,
        entity: str,
        title: str,
        relationships: dict[str, int | None],
        **values: object,
    ) -> object:
        self._write()
        if not any(relationships.values()):
            raise CrmError("At least one CRM relationship is required.")
        if "<" in title or ">" in title:
            raise CrmError("Unsafe HTML is not allowed.")
        if (
            entity == "task"
            and values.get("reminder_at")
            and values.get("due_at")
            and values["reminder_at"] > values["due_at"]
        ):
            raise CrmError("Reminder must not be after the due date.")
        field = (
            "content"
            if entity == "note"
            else "title"
            if entity == "task"
            else "subject"
        )
        result = self.repo.create(
            entity,
            {
                **relationships,
                **values,
                field: self._required(title),
                "status": values.get(
                    "status", "OPEN" if entity == "task" else "PLANNED"
                ),
                "created_by_user_id": self.user_id,
            },
        )
        self._audit(f"{entity.upper()}_CREATED", result)
        return result

    def complete(self, entity: str, entity_id: int) -> object:
        self._write()
        result = self.repo.update(
            entity,
            entity_id,
            {"status": "COMPLETED", "completed_at": datetime.now(UTC)},
        )
        self._audit(f"{entity.upper()}_COMPLETED", result)
        return result

    def list(self, entity: str, **filters: object) -> Page:
        self._read()
        return self.repo.list(entity, **filters)

    def metrics(self) -> dict[str, object]:
        self._read()
        return self.repo.metrics()

    def timeline(
        self, entity: str, entity_id: int, page: int = 1, page_size: int = 50
    ) -> tuple[object, ...]:
        self._read()
        return self.repo.timeline(entity, entity_id, page_size, (page - 1) * page_size)

    def search(self, query: str, limit: int = 25) -> dict[str, tuple[object, ...]]:
        self._read()
        return self.repo.search(query.strip(), min(max(limit, 1), 100))

    def preview_csv(self, content: bytes, max_rows: int = 1000) -> ImportPreview:
        self._manage()
        if len(content) > 2_000_000:
            raise CrmError("CSV file is too large.")
        try:
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise CrmError("CSV file is invalid.") from exc
        if len(rows) > max_rows:
            raise CrmError("CSV row limit exceeded.")
        valid, errors = [], []
        for number, row in enumerate(rows, 2):
            clean = {
                key: neutralize_formula(value.strip())
                for key, value in row.items()
                if key
            }
            if not clean.get("title"):
                errors.append(f"Row {number}: title is required.")
            else:
                valid.append(clean)
        return ImportPreview(tuple(valid), tuple(errors), ())

    def import_csv(self, content: bytes, dry_run: bool = True) -> ImportPreview:
        preview = self.preview_csv(content)
        if not dry_run:
            self._audit_raw("CSV_IMPORT_STARTED", "crm_import", "0")
            for row in preview.valid_rows:
                self.create_lead(
                    row["title"],
                    source=row.get("source") or "CSV_IMPORT",
                    industry=row.get("industry"),
                    country=row.get("country"),
                    city=row.get("city"),
                    website=row.get("website"),
                    email=row.get("contact_email"),
                    phone=row.get("contact_phone"),
                    priority=row.get("priority") or "MEDIUM",
                    estimated_value=Decimal(row.get("estimated_value") or 0),
                    currency=row.get("currency") or "INR",
                )
            self._audit_raw(
                "CSV_IMPORT_COMPLETED", "crm_import", str(len(preview.valid_rows))
            )
        return preview

    def export_csv(self, entity: str, **filters: object) -> bytes:
        page = self.list(entity, page=1, page_size=10_000, **filters)
        output = io.StringIO()
        writer = csv.writer(output)
        headers = {
            "lead": (
                "lead_number",
                "title",
                "source",
                "status",
                "qualification_status",
                "priority",
                "score",
                "estimated_value",
                "currency",
            ),
            "opportunity": (
                "opportunity_number",
                "name",
                "status",
                "amount",
                "currency",
                "probability_percentage",
                "weighted_amount",
            ),
            "contact": ("first_name", "last_name", "email", "phone", "status"),
            "task": ("title", "priority", "status", "due_at"),
        }[entity]
        writer.writerow(headers)
        for item in page.items:
            writer.writerow(
                neutralize_formula(getattr(item, key, "")) for key in headers
            )
        return output.getvalue().encode()

    def _get(self, entity: str, entity_id: int) -> object:
        result = self.repo.get(entity, entity_id)
        if result is None:
            raise CrmError(f"{entity.title()} is unavailable.")
        return result

    def _status(self, entity: str, entity_id: int, status: str, event: str) -> object:
        self._write()
        result = self.repo.update(
            entity, entity_id, {"status": status, "updated_by_user_id": self.user_id}
        )
        self._audit(event, result)
        return result

    def _read(self) -> None:
        if self.read:
            self.read()

    def _write(self) -> None:
        if self.write:
            self.write()

    def _manage(self) -> None:
        if self.manage:
            self.manage()

    def _audit(self, action: str, entity: object) -> None:
        self._audit_raw(action, type(entity).__name__, str(getattr(entity, "id", "")))

    def _audit_raw(self, action: str, entity: str, entity_id: str) -> None:
        if self.audit:
            self.audit(action, entity, entity_id)

    @staticmethod
    def _required(value: str) -> str:
        value = value.strip()
        if not value or len(value) > 500 or "<script" in value.casefold():
            raise CrmError("A valid value is required.")
        return value

    @staticmethod
    def _currency(value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise CrmError("Currency must be a three-letter code.")
        return value

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        value = Decimal(value).quantize(Decimal("0.01"))
        if value < 0:
            raise CrmError("Amount cannot be negative.")
        return value


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not re.search(r"\s", value)
    )
