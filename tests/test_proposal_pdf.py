from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from leadpilot.application.proposal_pdf import (
    ProposalPdfError,
    safe_pdf_filename,
    validate_pdf,
)
from leadpilot.application.proposal_pdf_snapshot import (
    OrganizationBrandingSnapshot,
    ProposalPdfSnapshot,
    canonical_json,
    safe_color,
    snapshot_hash,
)
from leadpilot.infrastructure.pdf.reportlab_proposal_renderer import (
    ReportLabProposalPdfRenderer,
)
from leadpilot.infrastructure.storage.local_document_storage import LocalDocumentStorage


def sample_snapshot(
    *, long: bool = False, branding_name: str = "Acme Consulting"
) -> ProposalPdfSnapshot:
    paragraph = "A consultative proposal based on confirmed client requirements. " * (
        100 if long else 2
    )
    items = tuple(
        {
            "id": index,
            "title": f"Service {index}",
            "description": paragraph,
            "quantity": Decimal("1.00"),
            "unit_price": Decimal("1000.00"),
            "discount": Decimal("50.00"),
            "tax_rate": Decimal("10.00"),
            "line_subtotal": Decimal("1000.00"),
            "line_tax": Decimal("95.00"),
            "line_total": Decimal("1045.00"),
            "timeline": "4 weeks",
        }
        for index in range(1, 16 if long else 4)
    )
    count = Decimal(len(items))
    return ProposalPdfSnapshot(
        OrganizationBrandingSnapshot(
            1,
            branding_name,
            None,
            None,
            "#123456",
            "#374151",
            "#22C55E",
            "https://tenant.example",
            "hello@tenant.example",
            None,
            "Thank you for considering our team.",
        ),
        {
            "id": 1,
            "number": "LP-2026-0042",
            "title": "Digital Operations Proposal",
            "status": "DRAFT",
            "issue_date": date(2026, 8, 1),
            "valid_until": date(2026, 8, 31),
            "currency": "USD",
            "updated_at": datetime(2026, 8, 1, tzinfo=UTC),
        },
        {
            "name": "Client's Healthcare Group",
            "industry": "Healthcare",
            "website": "https://client.example/long/path",
            "country": "India",
            "city": "Hyderabad",
        },
        tuple(
            {
                "key": key,
                "title": title,
                "content": paragraph,
                "content_source": "MANUAL",
                "manually_edited": True,
            }
            for key, title in (
                ("EXECUTIVE_SUMMARY", "Executive Summary"),
                ("SCOPE", "Scope of Work"),
                ("DELIVERABLES", "Deliverables"),
            )
        ),
        items,
        {
            "subtotal": Decimal("1000.00") * count,
            "discount": Decimal("50.00") * count,
            "tax": Decimal("95.00") * count,
            "total": Decimal("1045.00") * count,
            "currency": "USD",
        },
        {
            "generated_at": datetime.now(UTC),
            "generated_by_user_id": 2,
            "application": "LeadPilot AI",
        },
    )


def test_renderer_creates_parseable_deterministic_commercial_pdf() -> None:
    snapshot = sample_snapshot()
    content = ReportLabProposalPdfRenderer().render(snapshot, confidential=True)
    validation = validate_pdf(content, max_size=5_000_000, expected_text="LP-2026-0042")
    assert content.startswith(b"%PDF-")
    assert validation.page_count >= 2
    assert validation.file_size == len(content)


def test_long_pdf_spans_pages_and_missing_branding_is_safe() -> None:
    snapshot = sample_snapshot(
        long=True,
        branding_name="A Very Long Tenant Organization Name That Must Remain Readable In The Footer",
    )
    validation = validate_pdf(
        ReportLabProposalPdfRenderer().render(snapshot, confidential=False),
        max_size=15_000_000,
        expected_text="LP-2026-0042",
    )
    assert validation.page_count >= 4


def test_hash_is_stable_and_changes_for_visible_content() -> None:
    first = sample_snapshot()
    reordered = (
        ProposalPdfSnapshot(**dict(reversed(list(first.__dict__.items()))))
        if hasattr(first, "__dict__")
        else first
    )
    assert snapshot_hash(first) == snapshot_hash(reordered)
    changed = replace(first, proposal={**first.proposal, "title": "Changed"})
    assert snapshot_hash(first) != snapshot_hash(changed)
    assert '"subtotal":"3000.00"' in canonical_json(first)


def test_filename_color_storage_and_pdf_validation_safety(tmp_path) -> None:
    assert safe_pdf_filename("../../bad\\name", "42") == "bad-name.pdf"
    assert safe_color("not-color", "#111111") == "#111111"
    storage = LocalDocumentStorage(tmp_path)
    storage.save("organizations/1/file.pdf", b"data")
    assert storage.read("organizations/1/file.pdf") == b"data"
    with pytest.raises(ValueError):
        storage.save("../escape.pdf", b"bad")
    with pytest.raises(ProposalPdfError):
        validate_pdf(b"bad", max_size=100, expected_text="x")
