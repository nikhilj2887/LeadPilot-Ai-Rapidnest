from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from leadpilot.application.companies import Company

PAGE_SIZE = 10
SORT_OPTIONS = (
    "Recently Updated",
    "Name A-Z",
    "Name Z-A",
    "Recently Added",
    "Status",
)


@dataclass(frozen=True, slots=True)
class Page:
    items: list[Company]
    number: int
    count: int
    total_items: int


def filter_companies(
    companies: Sequence[Company],
    *,
    query: str = "",
    status: str = "All",
    industry: str = "All",
    country: str = "All",
) -> list[Company]:
    needle = query.strip().casefold()

    def matches(company: Company) -> bool:
        searchable = (
            company.name,
            company.website,
            company.industry,
            company.country,
            company.city,
        )
        return (
            not needle
            or any(needle in (value or "").casefold() for value in searchable)
        ) and all(
            (
                status == "All" or company.status == status,
                industry == "All" or company.industry == industry,
                country == "All" or company.country == country,
            )
        )

    return [company for company in companies if matches(company)]


def sort_companies(
    companies: Sequence[Company], option: str = "Recently Updated"
) -> list[Company]:
    if option == "Name A-Z":
        return sorted(companies, key=lambda company: company.name.casefold())
    if option == "Name Z-A":
        return sorted(
            companies, key=lambda company: company.name.casefold(), reverse=True
        )
    if option == "Recently Added":
        return sorted(companies, key=lambda company: company.created_at, reverse=True)
    if option == "Status":
        return sorted(
            companies, key=lambda company: (company.status, company.name.casefold())
        )
    return sorted(companies, key=lambda company: company.updated_at, reverse=True)


def paginate(
    companies: Sequence[Company], page: int, page_size: int = PAGE_SIZE
) -> list[Company]:
    safe_page = max(1, page)
    start = (safe_page - 1) * page_size
    return list(companies[start : start + page_size])


def build_page(
    companies: Sequence[Company], page: int, page_size: int = PAGE_SIZE
) -> Page:
    count = max(1, (len(companies) + page_size - 1) // page_size)
    number = min(max(1, page), count)
    return Page(paginate(companies, number, page_size), number, count, len(companies))
