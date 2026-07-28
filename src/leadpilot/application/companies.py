from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

COMPANY_SIZES = ("Solo", "2-10", "11-50", "51-200", "201-500", "501-1000", "1000+")
COMPANY_STATUSES = (
    "New",
    "Researching",
    "Qualified",
    "Contacted",
    "Proposal",
    "Won",
    "Lost",
)


class CompanyValidationError(ValueError):
    """Raised when company input is invalid."""


class CompanyNotFoundError(LookupError):
    """Raised when a requested company does not exist."""


@dataclass(frozen=True, slots=True)
class Company:
    id: int
    name: str
    website: str | None
    industry: str | None
    country: str | None
    city: str | None
    company_size: str | None
    status: str
    source: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    organization_id: int = 1


@dataclass(frozen=True, slots=True)
class CompanyMetrics:
    total: int
    new: int
    qualified: int
    contacted: int
    proposal: int
    by_status: dict[str, int]


class CompanyRepository(Protocol):
    def create(self, values: dict[str, str | None]) -> Company: ...
    def get_by_id(self, company_id: int) -> Company | None: ...
    def get_by_name(self, name: str) -> Company | None: ...
    def list_all(self) -> list[Company]: ...
    def search(self, query: str) -> list[Company]: ...
    def count(self) -> int: ...
    def update(
        self, company_id: int, values: dict[str, str | None]
    ) -> Company | None: ...
    def delete(self, company_id: int) -> bool: ...
    def count_by_status(self) -> dict[str, int]: ...
    def count_by_country(self) -> dict[str, int]: ...
    def count_by_industry(self) -> dict[str, int]: ...
    def list_recent(self, limit: int = 5) -> list[Company]: ...


class CompanyService:
    def __init__(self, repository: CompanyRepository) -> None:
        self._repository = repository

    def list_companies(self) -> list[Company]:
        return self._repository.list_all()

    def search_companies(self, query: str) -> list[Company]:
        return self._repository.search(query)

    def recent_companies(self, limit: int = 5) -> list[Company]:
        return self._repository.list_recent(limit)

    def get_company(self, company_id: int) -> Company:
        model = self._repository.get_by_id(company_id)
        if model is None:
            raise CompanyNotFoundError(f"Company {company_id} was not found")
        return model

    def create_company(
        self,
        *,
        name: str,
        website: str | None = None,
        industry: str | None = None,
        country: str | None = None,
        city: str | None = None,
        company_size: str | None = None,
        status: str = "New",
        source: str | None = None,
        notes: str | None = None,
    ) -> Company:
        values = self._validate(
            name, website, industry, country, city, company_size, status, source, notes
        )
        if self._repository.get_by_name(values["name"] or ""):
            raise CompanyValidationError("A company with this name already exists")
        return self._repository.create(values)

    def update_company(
        self,
        company_id: int,
        *,
        name: str,
        website: str | None = None,
        industry: str | None = None,
        country: str | None = None,
        city: str | None = None,
        company_size: str | None = None,
        status: str = "New",
        source: str | None = None,
        notes: str | None = None,
    ) -> Company:
        values = self._validate(
            name, website, industry, country, city, company_size, status, source, notes
        )
        existing = self._repository.get_by_name(values["name"] or "")
        if existing is not None and existing.id != company_id:
            raise CompanyValidationError("A company with this name already exists")
        model = self._repository.update(company_id, values)
        if model is None:
            raise CompanyNotFoundError(f"Company {company_id} was not found")
        return model

    def delete_company(self, company_id: int) -> None:
        if not self._repository.delete(company_id):
            raise CompanyNotFoundError(f"Company {company_id} was not found")

    def metrics(self) -> CompanyMetrics:
        counts = self._repository.count_by_status()
        return CompanyMetrics(
            total=self._repository.count(),
            new=counts.get("New", 0),
            qualified=counts.get("Qualified", 0),
            contacted=counts.get("Contacted", 0),
            proposal=counts.get("Proposal", 0),
            by_status={status: counts.get(status, 0) for status in COMPANY_STATUSES},
        )

    def counts_by_country(self) -> dict[str, int]:
        return self._repository.count_by_country()

    def counts_by_industry(self) -> dict[str, int]:
        return self._repository.count_by_industry()

    @staticmethod
    def normalize_website(website: str | None) -> str | None:
        clean = CompanyService._optional(website)
        if not clean:
            return None
        candidate = clean if "://" in clean else f"https://{clean}"
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise CompanyValidationError(
                "Website must be a valid domain or HTTP(S) URL"
            )
        if "." not in parsed.hostname and parsed.hostname != "localhost":
            raise CompanyValidationError(
                "Website must be a valid domain or HTTP(S) URL"
            )
        return candidate

    @staticmethod
    def _validate(
        name: str,
        website: str | None,
        industry: str | None,
        country: str | None,
        city: str | None,
        company_size: str | None,
        status: str,
        source: str | None,
        notes: str | None,
    ) -> dict[str, str | None]:
        clean_name = name.strip()
        if not clean_name:
            raise CompanyValidationError("Company name is required")
        if len(clean_name) > 200:
            raise CompanyValidationError("Company name must be 200 characters or fewer")
        clean_size = CompanyService._optional(company_size)
        if clean_size and clean_size not in COMPANY_SIZES:
            raise CompanyValidationError("Company size is invalid")
        if status not in COMPANY_STATUSES:
            raise CompanyValidationError("Company status is invalid")
        return {
            "name": clean_name,
            "website": CompanyService.normalize_website(website),
            "industry": CompanyService._optional(industry),
            "country": CompanyService._optional(country),
            "city": CompanyService._optional(city),
            "company_size": clean_size,
            "status": status,
            "source": CompanyService._optional(source),
            "notes": CompanyService._optional(notes),
        }

    @staticmethod
    def _optional(value: str | None) -> str | None:
        clean = value.strip() if value else ""
        return clean or None
