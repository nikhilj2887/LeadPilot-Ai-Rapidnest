from __future__ import annotations

from collections.abc import Callable

from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.pages import (
    companies,
    dashboard,
    discovery,
    proposals,
    settings,
)

PageRenderer = Callable[[Container], None]

PAGE_ICONS = {
    "Dashboard": "◫",
    "Companies": "▦",
    "Discovery": "⌕",
    "Proposals": "▤",
    "Settings": "⚙",
}

PAGES: dict[str, PageRenderer] = {
    "Dashboard": dashboard.render,
    "Companies": companies.render,
    "Discovery": discovery.render,
    "Proposals": proposals.render,
    "Settings": settings.render,
}


def navigation_label(page: str) -> str:
    return f"{PAGE_ICONS[page]}  {page}"
