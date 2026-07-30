import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "leadpilot.presentation.streamlit.app",
        "leadpilot.presentation.streamlit.navigation",
        "leadpilot.presentation.streamlit.views.dashboard",
        "leadpilot.presentation.streamlit.views.companies",
        "leadpilot.presentation.streamlit.views.discovery",
        "leadpilot.presentation.streamlit.views.proposals",
        "leadpilot.presentation.streamlit.views.service_catalog",
        "leadpilot.presentation.streamlit.views.settings",
        "leadpilot.presentation.streamlit.views.team",
        "leadpilot.presentation.streamlit.views.platform_admin",
        "leadpilot.presentation.streamlit.auth_ui",
    ],
)
def test_streamlit_module_imports_without_rendering(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None
