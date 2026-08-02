from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_TIMER_COMPONENT = components.declare_component(
    "leadpilot_engagement_timer",
    path=str(Path(__file__).with_name("engagement_timer")),
)


def engagement_timer(*, key: str) -> dict[str, int] | None:
    """Return bounded elapsed-time samples from a local page timer."""
    value = _TIMER_COMPONENT(key=key, default=None)
    if not isinstance(value, dict):
        return None
    sequence, duration = value.get("sequence"), value.get("duration_ms")
    if not isinstance(sequence, int) or not isinstance(duration, int):
        return None
    return {"sequence": sequence, "duration_ms": duration}
