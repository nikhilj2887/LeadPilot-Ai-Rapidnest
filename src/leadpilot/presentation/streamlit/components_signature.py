from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_SIGNATURE_COMPONENT = components.declare_component(
    "leadpilot_signature_pad",
    path=str(Path(__file__).with_name("signature_pad")),
)


def signature_pad(*, key: str) -> str | None:
    """Render a local, dependency-free HTML canvas and return a PNG data URL."""
    value = _SIGNATURE_COMPONENT(key=key, default=None)
    return value if isinstance(value, str) else None
