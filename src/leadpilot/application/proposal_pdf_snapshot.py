from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from leadpilot.application.catalog_candidate_scoring import sanitize_evidence

NEUTRAL_COLORS = ("#1F2937", "#374151", "#2563EB")


@dataclass(frozen=True, slots=True)
class OrganizationBrandingSnapshot:
    organization_id: int
    display_name: str
    legal_name: str | None
    logo_path: str | None
    primary_color: str
    secondary_color: str
    accent_color: str
    website: str | None
    email: str | None
    phone: str | None
    footer: str | None


@dataclass(frozen=True, slots=True)
class ProposalPdfSnapshot:
    branding: OrganizationBrandingSnapshot
    proposal: dict[str, Any]
    client: dict[str, Any]
    sections: tuple[dict[str, Any], ...]
    items: tuple[dict[str, Any], ...]
    commercial: dict[str, Any]
    metadata: dict[str, Any]


def safe_color(value: str | None, fallback: str) -> str:
    return (
        value.upper() if value and re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else fallback
    )


def canonical_json(value: Any) -> str:
    def convert(item: Any) -> Any:
        if is_dataclass(item):
            return convert(asdict(item))
        if isinstance(item, Decimal):
            return format(item, "f")
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, dict):
            return {key: convert(item[key]) for key in sorted(item)}
        if isinstance(item, (list, tuple)):
            return [convert(entry) for entry in item]
        return item

    return json.dumps(
        convert(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def snapshot_hash(snapshot: ProposalPdfSnapshot) -> str:
    stable = asdict(snapshot)
    stable["metadata"].pop("generated_at", None)
    return hashlib.sha256(canonical_json(stable).encode()).hexdigest()


class ProposalPdfSnapshotBuilder:
    def __init__(
        self,
        proposals: object,
        companies: object,
        organization_context: object,
        organizations: object,
        user_id: int | None = None,
    ) -> None:
        self._proposals, self._companies = proposals, companies
        self._context, self._organizations, self._user_id = (
            organization_context,
            organizations,
            user_id,
        )

    def build(self, proposal_id: int) -> ProposalPdfSnapshot:
        proposal = self._proposals.get_proposal(proposal_id)
        company = self._companies.get_company(proposal.company_id)
        organization = self._context.organization
        branding = self._organizations.get_branding(organization.id)
        colors = NEUTRAL_COLORS
        brand = OrganizationBrandingSnapshot(
            organization.id,
            branding.brand_name if branding else organization.display_name,
            organization.legal_name,
            self._safe_logo(branding.logo_reference if branding else None),
            safe_color(branding.primary_color if branding else None, colors[0]),
            safe_color(branding.secondary_color if branding else None, colors[1]),
            safe_color(branding.accent_color if branding else None, colors[2]),
            organization.website,
            organization.contact_email,
            organization.contact_phone,
            sanitize_evidence(branding.proposal_footer, 1000)
            if branding and branding.proposal_footer
            else None,
        )
        sections = tuple(
            {
                "key": section.section_key,
                "title": sanitize_evidence(section.title, 200),
                "content": sanitize_evidence(section.content, 20000),
                "content_source": section.content_source,
                "manually_edited": section.manually_edited,
            }
            for section in self._proposals.list_sections(proposal_id)
            if section.is_enabled and section.content.strip()
        )
        items = tuple(
            {
                "id": item.id,
                "title": sanitize_evidence(item.title, 300),
                "description": sanitize_evidence(item.description or "", 3000),
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "discount": item.discount_amount,
                "tax_rate": item.tax_rate,
                "line_subtotal": item.line_subtotal,
                "line_tax": item.line_tax,
                "line_total": item.line_total,
                "timeline": item.delivery_timeline,
            }
            for item in self._proposals.list_items(proposal_id)
            if not item.is_optional
        )
        item_subtotal = sum((item["line_subtotal"] for item in items), Decimal(0))
        item_discount = sum((item["discount"] for item in items), Decimal(0))
        item_tax = sum((item["line_tax"] for item in items), Decimal(0))
        item_total = sum((item["line_total"] for item in items), Decimal(0))
        if (item_subtotal, item_discount, item_tax, item_total) != (
            proposal.subtotal,
            proposal.discount_amount,
            proposal.tax_amount,
            proposal.total_amount,
        ):
            raise ValueError(
                "Proposal commercial totals are inconsistent with line items."
            )
        return ProposalPdfSnapshot(
            brand,
            {
                "id": proposal.id,
                "number": proposal.proposal_number,
                "title": sanitize_evidence(proposal.title, 300),
                "status": proposal.status.value,
                "issue_date": proposal.created_at.date(),
                "valid_until": proposal.valid_until,
                "currency": proposal.currency,
                "updated_at": proposal.updated_at,
            },
            {
                "name": company.name,
                "industry": company.industry,
                "website": company.website,
                "country": company.country,
                "city": company.city,
            },
            sections,
            items,
            {
                "subtotal": proposal.subtotal,
                "discount": proposal.discount_amount,
                "tax": proposal.tax_amount,
                "total": proposal.total_amount,
                "currency": proposal.currency,
            },
            {
                "generated_at": datetime.now().astimezone(),
                "generated_by_user_id": self._user_id,
                "application": "LeadPilot AI",
            },
        )

    @staticmethod
    def _safe_logo(reference: str | None) -> str | None:
        if not reference or reference.startswith(("http://", "https://")):
            return None
        path = __import__("pathlib").Path(reference)
        if (
            path.suffix.lower() not in {".png", ".jpg", ".jpeg"}
            or not path.is_file()
            or path.stat().st_size > 2 * 1024 * 1024
        ):
            return None
        return str(path.resolve())
