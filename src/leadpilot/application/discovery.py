from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from leadpilot.application.companies import CompanyNotFoundError, CompanyRepository

DISCOVERY_STATUSES = ("Pending", "Running", "Completed", "Failed")


class DiscoveryError(ValueError):
    """A safe, user-facing discovery error."""


@dataclass(frozen=True, slots=True)
class DiscoveryScan:
    id: int
    company_id: int
    website_url: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    data: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def __getattr__(self, name: str) -> Any:
        if name in self.data:
            return self.data[name]
        raise AttributeError(name)


@dataclass(frozen=True, slots=True)
class DiscoverySummary:
    total: int
    completed: int
    failed: int
    average_lead_priority: float
    high_priority: int
    average_automation_potential: float
    recent: list[DiscoveryScan] = field(default_factory=list)


class DiscoveryRepository(Protocol):
    def create(self, company_id: int, website_url: str) -> DiscoveryScan: ...
    def get_by_id(self, scan_id: int) -> DiscoveryScan | None: ...
    def update_status(self, scan_id: int, status: str) -> DiscoveryScan: ...
    def save_completed_result(
        self, scan_id: int, values: dict[str, Any]
    ) -> DiscoveryScan: ...
    def save_failed_result(self, scan_id: int, message: str) -> DiscoveryScan: ...
    def get_latest_by_company(self, company_id: int) -> DiscoveryScan | None: ...
    def list_by_company(self, company_id: int) -> list[DiscoveryScan]: ...
    def list_recent(self, limit: int = 50) -> list[DiscoveryScan]: ...
    def summary(self) -> DiscoverySummary: ...


class Scanner(Protocol):
    def scan(self, website_url: str) -> dict[str, Any]: ...


class DiscoveryService:
    def __init__(
        self,
        repository: DiscoveryRepository,
        companies: CompanyRepository,
        scanner: Scanner,
    ) -> None:
        self._repository = repository
        self._companies = companies
        self._scanner = scanner

    def run_scan(
        self, company_id: int, website_url: str | None = None
    ) -> DiscoveryScan:
        company = self._companies.get_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError(f"Company {company_id} was not found")
        target = (website_url or company.website or "").strip()
        if not target:
            raise DiscoveryError("Enter a website URL before running discovery.")
        scan = self._repository.create(company_id, target)
        self._repository.update_status(scan.id, "Running")
        try:
            result = self._scanner.scan(target)
        except DiscoveryError as exc:
            return self._repository.save_failed_result(scan.id, str(exc))
        except Exception:  # noqa: BLE001 - persistence must close every handled scan
            return self._repository.save_failed_result(
                scan.id, "The website scan could not be completed safely."
            )
        return self._repository.save_completed_result(scan.id, result)

    def get_scan(self, scan_id: int) -> DiscoveryScan:
        scan = self._repository.get_by_id(scan_id)
        if scan is None:
            raise DiscoveryError("That discovery report is no longer available.")
        return scan

    def latest_for_company(self, company_id: int) -> DiscoveryScan | None:
        return self._repository.get_latest_by_company(company_id)

    def history_for_company(self, company_id: int) -> list[DiscoveryScan]:
        return self._repository.list_by_company(company_id)

    def recent_scans(self, limit: int = 50) -> list[DiscoveryScan]:
        return self._repository.list_recent(limit)

    def dashboard_summary(self) -> DiscoverySummary:
        return self._repository.summary()


def utcnow() -> datetime:
    return datetime.now(UTC)
