from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

MONEY = Decimal("0.01")


class ProposalStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    SENT = "SENT"
    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class ProposalItemType(StrEnum):
    PRODUCT = "PRODUCT"
    SERVICE = "SERVICE"
    SUBSCRIPTION = "SUBSCRIPTION"
    SUPPORT = "SUPPORT"
    CONSULTING = "CONSULTING"
    TRAINING = "TRAINING"
    CUSTOM = "CUSTOM"


class ProposalSort(StrEnum):
    UPDATED = "UPDATED"
    CREATED = "CREATED"
    NUMBER = "NUMBER"
    TITLE = "TITLE"
    TOTAL = "TOTAL"


class ProposalValidationError(ValueError):
    """Raised when proposal input violates a business rule."""


class ProposalNotFoundError(LookupError):
    """Raised when a proposal is unavailable in the selected organization."""


class ProposalInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    company_id: int = Field(gt=0)
    discovery_scan_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=300)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    valid_until: date | None = None
    summary: str | None = None
    client_requirements: str | None = None
    recommended_approach: str | None = None
    implementation_plan: str | None = None
    commercial_notes: str | None = None
    terms_and_conditions: str | None = None
    internal_notes: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if not value.isalpha():
            raise ValueError("Currency must be a three-letter code")
        return value.upper()


class ProposalItemInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    item_type: ProposalItemType = ProposalItemType.CUSTOM
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    quantity: Decimal = Field(default=Decimal(1), gt=0, max_digits=12, decimal_places=2)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    discount_amount: Decimal = Field(
        default=Decimal(0), ge=0, max_digits=14, decimal_places=2
    )
    tax_rate: Decimal = Field(
        default=Decimal(0), ge=0, le=100, max_digits=7, decimal_places=4
    )
    delivery_timeline: str | None = Field(default=None, max_length=200)
    selection_reason: str | None = None
    is_optional: bool = False
    display_order: int = Field(default=0, ge=0)


class ProposalSectionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    content: str = ""
    is_enabled: bool = True
    display_order: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class Proposal:
    id: int
    organization_id: int
    company_id: int
    company_name: str
    discovery_scan_id: int | None
    proposal_number: str
    title: str
    status: ProposalStatus
    currency: str
    valid_until: date | None
    summary: str | None
    client_requirements: str | None
    recommended_approach: str | None
    implementation_plan: str | None
    commercial_notes: str | None
    terms_and_conditions: str | None
    internal_notes: str | None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProposalItem:
    id: int
    proposal_id: int
    service_catalog_id: int | None
    item_type: ProposalItemType
    title: str
    description: str | None
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    line_subtotal: Decimal
    line_tax: Decimal
    line_total: Decimal
    delivery_timeline: str | None
    selection_reason: str | None
    is_optional: bool
    display_order: int


@dataclass(frozen=True, slots=True)
class ProposalSection:
    id: int
    proposal_id: int
    section_key: str
    title: str
    content: str
    is_enabled: bool
    display_order: int


@dataclass(frozen=True, slots=True)
class ProposalVersion:
    id: int
    proposal_id: int
    version_number: int
    snapshot: dict[str, Any]
    change_summary: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProposalActivity:
    id: int
    proposal_id: int
    activity_type: str
    details: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProposalFilters:
    query: str = ""
    company_id: int | None = None
    status: ProposalStatus | None = None
    created_from: date | None = None
    created_to: date | None = None


@dataclass(frozen=True, slots=True)
class ProposalPage:
    items: tuple[Proposal, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class ProposalMetrics:
    total: int
    drafts: int
    in_review: int
    accepted: int
    pipeline_value: Decimal


DEFAULT_SECTIONS = (
    ("EXECUTIVE_SUMMARY", "Executive Summary"),
    ("CLIENT_REQUIREMENTS", "Client Requirements"),
    ("RECOMMENDED_APPROACH", "Recommended Approach"),
    ("SCOPE", "Scope of Work"),
    ("DELIVERABLES", "Deliverables"),
    ("TIMELINE", "Implementation Timeline"),
    ("TEAM", "Project Team"),
    ("PRICING", "Pricing"),
    ("ASSUMPTIONS", "Assumptions"),
    ("CLIENT_RESPONSIBILITIES", "Client Responsibilities"),
    ("TERMS", "Terms and Conditions"),
    ("WHY_US", "Why LeadPilot AI"),
    ("NEXT_STEPS", "Next Steps"),
    ("APPENDIX", "Appendix"),
)

TRANSITIONS: dict[ProposalStatus, frozenset[ProposalStatus]] = {
    ProposalStatus.DRAFT: frozenset(
        {ProposalStatus.IN_REVIEW, ProposalStatus.ARCHIVED}
    ),
    ProposalStatus.IN_REVIEW: frozenset(
        {ProposalStatus.DRAFT, ProposalStatus.APPROVED, ProposalStatus.ARCHIVED}
    ),
    ProposalStatus.APPROVED: frozenset(
        {ProposalStatus.DRAFT, ProposalStatus.SENT, ProposalStatus.ARCHIVED}
    ),
    ProposalStatus.SENT: frozenset(
        {
            ProposalStatus.VIEWED,
            ProposalStatus.ACCEPTED,
            ProposalStatus.REJECTED,
            ProposalStatus.EXPIRED,
        }
    ),
    ProposalStatus.VIEWED: frozenset(
        {ProposalStatus.ACCEPTED, ProposalStatus.REJECTED, ProposalStatus.EXPIRED}
    ),
    ProposalStatus.REJECTED: frozenset({ProposalStatus.DRAFT, ProposalStatus.ARCHIVED}),
    ProposalStatus.EXPIRED: frozenset({ProposalStatus.DRAFT, ProposalStatus.ARCHIVED}),
    ProposalStatus.ARCHIVED: frozenset({ProposalStatus.DRAFT}),
    ProposalStatus.ACCEPTED: frozenset({ProposalStatus.ARCHIVED}),
}


class ProposalRepository(Protocol):
    def company_exists(self, company_id: int) -> bool: ...
    def scan_company_id(self, scan_id: int) -> int | None: ...
    def catalog_item(
        self, item_id: int
    ) -> tuple[str, str | None, Decimal | None, str, bool] | None: ...
    def next_number(self, year: int) -> str: ...
    def create(
        self, values: ProposalInput, number: str, user_id: int | None
    ) -> Proposal: ...
    def get(self, proposal_id: int) -> Proposal | None: ...
    def update(
        self, proposal_id: int, values: ProposalInput, user_id: int | None
    ) -> Proposal | None: ...
    def delete(self, proposal_id: int) -> bool: ...
    def transition(
        self, proposal_id: int, status: ProposalStatus, user_id: int | None
    ) -> Proposal | None: ...
    def list(
        self,
        filters: ProposalFilters,
        *,
        page: int,
        page_size: int,
        sort: ProposalSort,
        descending: bool,
    ) -> ProposalPage: ...
    def metrics(self) -> ProposalMetrics: ...
    def add_item(
        self, proposal_id: int, values: ProposalItemInput, catalog_id: int | None
    ) -> ProposalItem: ...
    def update_item(
        self, proposal_id: int, item_id: int, values: ProposalItemInput
    ) -> ProposalItem | None: ...
    def delete_item(self, proposal_id: int, item_id: int) -> bool: ...
    def list_items(self, proposal_id: int) -> tuple[ProposalItem, ...]: ...
    def reorder_items(self, proposal_id: int, item_ids: list[int]) -> bool: ...
    def add_section(
        self, proposal_id: int, key: str, values: ProposalSectionInput
    ) -> ProposalSection: ...
    def update_section(
        self, proposal_id: int, section_id: int, values: ProposalSectionInput
    ) -> ProposalSection | None: ...
    def list_sections(self, proposal_id: int) -> tuple[ProposalSection, ...]: ...
    def reorder_sections(self, proposal_id: int, section_ids: list[int]) -> bool: ...
    def create_version(
        self,
        proposal_id: int,
        snapshot: dict[str, Any],
        summary: str | None,
        user_id: int | None,
    ) -> ProposalVersion: ...
    def list_versions(self, proposal_id: int) -> tuple[ProposalVersion, ...]: ...
    def add_activity(
        self,
        proposal_id: int,
        activity_type: str,
        details: dict[str, Any],
        user_id: int | None,
    ) -> None: ...
    def list_activities(self, proposal_id: int) -> tuple[ProposalActivity, ...]: ...


class ProposalService:
    """Tenant-safe proposal workflow and deterministic commercial calculations."""

    def __init__(
        self,
        repository: ProposalRepository,
        *,
        user_id: int | None = None,
        authorize_write: Callable[[], None] | None = None,
        audit: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._repository = repository
        self._user_id = user_id
        self._authorize_write = authorize_write
        self._audit = audit

    def create_proposal(self, values: ProposalInput) -> Proposal:
        self._authorize()
        self._validate_context(values)
        proposal = self._repository.create(
            values,
            self._repository.next_number(datetime.now(UTC).year),
            self._user_id,
        )
        for order, (key, title) in enumerate(DEFAULT_SECTIONS):
            self._repository.add_section(
                proposal.id, key, ProposalSectionInput(title=title, display_order=order)
            )
        self._record(
            proposal.id, "CREATED", {"proposal_number": proposal.proposal_number}
        )
        return proposal

    def get_proposal(self, proposal_id: int) -> Proposal:
        proposal = self._repository.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(f"Proposal {proposal_id} was not found")
        return proposal

    def update_proposal(self, proposal_id: int, values: ProposalInput) -> Proposal:
        self._authorize()
        self._ensure_editable(self.get_proposal(proposal_id))
        self._validate_context(values)
        proposal = self._repository.update(proposal_id, values, self._user_id)
        if proposal is None:
            raise ProposalNotFoundError(f"Proposal {proposal_id} was not found")
        self._record(proposal_id, "UPDATED", {})
        return proposal

    def delete_proposal(self, proposal_id: int) -> None:
        self._authorize()
        proposal = self.get_proposal(proposal_id)
        if proposal.status == ProposalStatus.ACCEPTED:
            raise ProposalValidationError("Accepted proposals cannot be deleted")
        if not self._repository.delete(proposal_id):
            raise ProposalNotFoundError(f"Proposal {proposal_id} was not found")
        self._audit_log("DELETE_PROPOSAL", proposal_id)

    def transition_status(self, proposal_id: int, status: ProposalStatus) -> Proposal:
        self._authorize()
        proposal = self.get_proposal(proposal_id)
        if status not in TRANSITIONS[proposal.status]:
            raise ProposalValidationError(f"Cannot move {proposal.status} to {status}")
        changed = self._repository.transition(proposal_id, status, self._user_id)
        if changed is None:
            raise ProposalNotFoundError(f"Proposal {proposal_id} was not found")
        self._record(
            proposal_id,
            "STATUS_CHANGED",
            {"from": proposal.status.value, "to": status.value},
        )
        return changed

    def archive_proposal(self, proposal_id: int) -> Proposal:
        return self.transition_status(proposal_id, ProposalStatus.ARCHIVED)

    def restore_proposal(self, proposal_id: int) -> Proposal:
        proposal = self.get_proposal(proposal_id)
        if proposal.status != ProposalStatus.ARCHIVED:
            raise ProposalValidationError("Only archived proposals can be restored")
        return self.transition_status(proposal_id, ProposalStatus.DRAFT)

    def list_proposals(
        self,
        filters: ProposalFilters | None = None,
        *,
        page: int = 1,
        page_size: int = 25,
        sort: ProposalSort = ProposalSort.UPDATED,
        descending: bool = True,
    ) -> ProposalPage:
        if page < 1 or not 1 <= page_size <= 100:
            raise ProposalValidationError("Invalid pagination")
        return self._repository.list(
            filters or ProposalFilters(),
            page=page,
            page_size=page_size,
            sort=sort,
            descending=descending,
        )

    def search_proposals(self, query: str, **kwargs: Any) -> ProposalPage:
        return self.list_proposals(ProposalFilters(query=query), **kwargs)

    def metrics(self) -> ProposalMetrics:
        return self._repository.metrics()

    def add_manual_item(
        self, proposal_id: int, values: ProposalItemInput
    ) -> ProposalItem:
        return self._add_item(proposal_id, values, None)

    def add_catalog_item(
        self,
        proposal_id: int,
        catalog_id: int,
        *,
        quantity: Decimal = Decimal(1),
        tax_rate: Decimal = Decimal(0),
        discount_amount: Decimal = Decimal(0),
        is_optional: bool = False,
    ) -> ProposalItem:
        catalog = self._repository.catalog_item(catalog_id)
        if catalog is None or not catalog[4]:
            raise ProposalValidationError("Catalog item is unavailable")
        proposal = self.get_proposal(proposal_id)
        name, description, price, currency, _ = catalog
        if currency != proposal.currency:
            raise ProposalValidationError("Catalog and proposal currencies must match")
        values = ProposalItemInput(
            item_type=ProposalItemType.SERVICE,
            title=name,
            description=description,
            quantity=quantity,
            unit_price=price or Decimal(0),
            discount_amount=discount_amount,
            tax_rate=tax_rate,
            is_optional=is_optional,
        )
        return self._add_item(proposal_id, values, catalog_id)

    def update_item(
        self, proposal_id: int, item_id: int, values: ProposalItemInput
    ) -> ProposalItem:
        self._authorize()
        self._ensure_editable(self.get_proposal(proposal_id))
        self._validate_line(values)
        item = self._repository.update_item(proposal_id, item_id, values)
        if item is None:
            raise ProposalNotFoundError(f"Proposal item {item_id} was not found")
        self._record(proposal_id, "ITEM_UPDATED", {"item_id": item_id})
        return item

    def delete_item(self, proposal_id: int, item_id: int) -> None:
        self._authorize()
        self._ensure_editable(self.get_proposal(proposal_id))
        if not self._repository.delete_item(proposal_id, item_id):
            raise ProposalNotFoundError(f"Proposal item {item_id} was not found")
        self._record(proposal_id, "ITEM_DELETED", {"item_id": item_id})

    def list_items(self, proposal_id: int) -> tuple[ProposalItem, ...]:
        self.get_proposal(proposal_id)
        return self._repository.list_items(proposal_id)

    def reorder_items(self, proposal_id: int, item_ids: list[int]) -> None:
        self._authorize()
        self._ensure_editable(self.get_proposal(proposal_id))
        if not self._repository.reorder_items(proposal_id, item_ids):
            raise ProposalValidationError(
                "Item order must contain every proposal item once"
            )

    def update_section(
        self, proposal_id: int, section_id: int, values: ProposalSectionInput
    ) -> ProposalSection:
        self._authorize()
        self._ensure_editable(self.get_proposal(proposal_id))
        section = self._repository.update_section(proposal_id, section_id, values)
        if section is None:
            raise ProposalNotFoundError(f"Proposal section {section_id} was not found")
        self._record(proposal_id, "SECTION_UPDATED", {"section_id": section_id})
        return section

    def list_sections(self, proposal_id: int) -> tuple[ProposalSection, ...]:
        self.get_proposal(proposal_id)
        return self._repository.list_sections(proposal_id)

    def reorder_sections(self, proposal_id: int, section_ids: list[int]) -> None:
        self._authorize()
        self._ensure_editable(self.get_proposal(proposal_id))
        if not self._repository.reorder_sections(proposal_id, section_ids):
            raise ProposalValidationError(
                "Section order must contain every section once"
            )

    def create_version(
        self, proposal_id: int, change_summary: str | None = None
    ) -> ProposalVersion:
        self._authorize()
        proposal = self.get_proposal(proposal_id)
        snapshot = {
            "proposal": self._json(asdict(proposal)),
            "items": self._json(
                [asdict(item) for item in self.list_items(proposal_id)]
            ),
            "sections": self._json(
                [asdict(section) for section in self.list_sections(proposal_id)]
            ),
        }
        version = self._repository.create_version(
            proposal_id, snapshot, change_summary, self._user_id
        )
        self._record(
            proposal_id, "VERSION_CREATED", {"version": version.version_number}
        )
        return version

    def list_versions(self, proposal_id: int) -> tuple[ProposalVersion, ...]:
        self.get_proposal(proposal_id)
        return self._repository.list_versions(proposal_id)

    def list_activities(self, proposal_id: int) -> tuple[ProposalActivity, ...]:
        self.get_proposal(proposal_id)
        return self._repository.list_activities(proposal_id)

    def _add_item(
        self, proposal_id: int, values: ProposalItemInput, catalog_id: int | None
    ) -> ProposalItem:
        self._authorize()
        self._ensure_editable(self.get_proposal(proposal_id))
        self._validate_line(values)
        item = self._repository.add_item(proposal_id, values, catalog_id)
        self._record(proposal_id, "ITEM_ADDED", {"item_id": item.id})
        return item

    @staticmethod
    def calculate_line(values: ProposalItemInput) -> tuple[Decimal, Decimal, Decimal]:
        subtotal = (values.quantity * values.unit_price).quantize(MONEY, ROUND_HALF_UP)
        taxable = subtotal - values.discount_amount
        if taxable < 0:
            raise ProposalValidationError("Discount cannot exceed the line subtotal")
        tax = (taxable * values.tax_rate / Decimal(100)).quantize(MONEY, ROUND_HALF_UP)
        return subtotal, tax, (taxable + tax).quantize(MONEY, ROUND_HALF_UP)

    def _validate_line(self, values: ProposalItemInput) -> None:
        self.calculate_line(values)

    def _validate_context(self, values: ProposalInput) -> None:
        if not self._repository.company_exists(values.company_id):
            raise ProposalValidationError("Company is unavailable in this organization")
        if (
            values.discovery_scan_id is not None
            and self._repository.scan_company_id(values.discovery_scan_id)
            != values.company_id
        ):
            raise ProposalValidationError(
                "Discovery scan must belong to the selected company"
            )

    @staticmethod
    def _ensure_editable(proposal: Proposal) -> None:
        if proposal.status in {ProposalStatus.ACCEPTED, ProposalStatus.ARCHIVED}:
            raise ProposalValidationError(
                f"{proposal.status.value.title()} proposals cannot be edited"
            )

    def _record(self, proposal_id: int, activity: str, details: dict[str, Any]) -> None:
        self._repository.add_activity(proposal_id, activity, details, self._user_id)
        self._audit_log(activity, proposal_id)

    def _audit_log(self, action: str, proposal_id: int) -> None:
        if self._audit:
            self._audit(action, "proposal", str(proposal_id))

    def _authorize(self) -> None:
        if self._authorize_write:
            self._authorize_write()

    @classmethod
    def _json(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._json(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json(item) for item in value]
        if isinstance(value, (Decimal, date, datetime, StrEnum)):
            return str(value)
        return value
