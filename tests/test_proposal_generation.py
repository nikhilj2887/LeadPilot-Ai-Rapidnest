from __future__ import annotations

import pytest

from leadpilot.application.ai_foundation import AISchemaValidationError
from leadpilot.application.proposal_context_builder import ProposalGenerationContext
from leadpilot.application.proposal_generation import (
    SUPPORTED_SECTION_KEYS,
    validate_generation_output,
)


def context() -> ProposalGenerationContext:
    return ProposalGenerationContext(
        proposal={},
        prospect={},
        seller={},
        recommendations=(),
        proposal_items=(),
        existing_sections=(),
        allowed_source_ids=frozenset({"company:1", "proposal_item:2"}),
        warnings=(),
    )


def section(key: str = "EXECUTIVE_SUMMARY", **overrides):
    value = {
        "section_key": key,
        "title": "Executive Summary",
        "content": "Acme has an observable opportunity to improve its enquiry journey.",
        "source_references": [
            {
                "source_type": "COMPANY",
                "source_id": "company:1",
                "description": "Company profile",
            }
        ],
        "warnings": [],
    }
    value.update(overrides)
    return value


def test_supported_sections_exclude_commercial_keys() -> None:
    assert "EXECUTIVE_SUMMARY" in SUPPORTED_SECTION_KEYS
    assert (
        not {
            "PRICING",
            "COMMERCIALS",
            "TAX",
            "TOTALS",
            "VALIDITY",
        }
        & SUPPORTED_SECTION_KEYS
    )


def test_generation_validation_accepts_requested_sections_and_sources() -> None:
    sections, warnings = validate_generation_output(
        {"sections": [section()], "global_warnings": ["Confirm internal process"]},
        ("EXECUTIVE_SUMMARY",),
        context(),
    )
    assert sections[0].section_key == "EXECUTIVE_SUMMARY"
    assert warnings == ("Confirm internal process",)


@pytest.mark.parametrize(
    "raw",
    (
        section("UNKNOWN"),
        section(content=""),
        section(
            source_references=[{"source_type": "COMPANY", "source_id": "company:9"}]
        ),
        section(price=100),
        section(content="<script>bad()</script> Guarantee 50% ROI"),
    ),
)
def test_generation_validation_rejects_unknown_empty_cross_context_and_commercial(
    raw,
) -> None:
    with pytest.raises(AISchemaValidationError):
        validate_generation_output(
            {"sections": [raw], "global_warnings": []},
            ("EXECUTIVE_SUMMARY",),
            context(),
        )


def test_duplicate_sections_rejected_and_missing_section_warned() -> None:
    with pytest.raises(AISchemaValidationError):
        validate_generation_output(
            {"sections": [section(), section()], "global_warnings": []},
            ("EXECUTIVE_SUMMARY",),
            context(),
        )
    sections, warnings = validate_generation_output(
        {"sections": [], "global_warnings": []},
        ("EXECUTIVE_SUMMARY",),
        context(),
    )
    assert sections == ()
    assert "omitted" in warnings[0]
