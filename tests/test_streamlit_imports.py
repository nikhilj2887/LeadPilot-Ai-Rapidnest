import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "leadpilot.presentation.streamlit.app",
        "leadpilot.presentation.streamlit.navigation",
        "leadpilot.presentation.streamlit.pages.dashboard",
        "leadpilot.presentation.streamlit.pages.companies",
        "leadpilot.presentation.streamlit.pages.discovery",
        "leadpilot.presentation.streamlit.pages.proposals",
        "leadpilot.presentation.streamlit.pages.settings",
    ],
)
def test_streamlit_module_imports_without_rendering(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None
