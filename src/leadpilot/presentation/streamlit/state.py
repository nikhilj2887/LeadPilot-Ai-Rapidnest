from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

FILTER_DEFAULTS: dict[str, Any] = {
    "company_search": "",
    "company_status": "All",
    "company_industry": "All",
    "company_country": "All",
    "company_sort": "Recently Updated",
}


def reset_company_filters(state: MutableMapping[str, Any]) -> None:
    state.update(FILTER_DEFAULTS)
    state["company_page"] = 1
    state.pop("company_filter_signature", None)


def sync_filter_page(
    state: MutableMapping[str, Any], signature: tuple[str, ...]
) -> None:
    if state.get("company_filter_signature") != signature:
        state["company_page"] = 1
        state["company_filter_signature"] = signature


def open_company_mode(
    state: MutableMapping[str, Any], mode: str, company_id: int | None = None
) -> None:
    state["company_mode"] = mode
    if company_id is None:
        state.pop("selected_company", None)
    else:
        state["selected_company"] = company_id


def return_to_company_list(state: MutableMapping[str, Any]) -> None:
    open_company_mode(state, "list")


def navigate(state: MutableMapping[str, Any], page: str) -> None:
    state["navigation"] = page
