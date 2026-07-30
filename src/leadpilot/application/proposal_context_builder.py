from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from leadpilot.application.catalog_candidate_scoring import sanitize_evidence
from leadpilot.application.offering_recommendations import RecommendationStatus


@dataclass(frozen=True, slots=True)
class ProposalGenerationContext:
    proposal: dict[str, Any]
    prospect: dict[str, Any]
    seller: dict[str, Any]
    recommendations: tuple[dict[str, Any], ...]
    proposal_items: tuple[dict[str, Any], ...]
    existing_sections: tuple[dict[str, Any], ...]
    allowed_source_ids: frozenset[str]
    warnings: tuple[str, ...]


class ProposalContextBuilder:
    """Builds bounded tenant context without commercial values or internal notes."""

    def __init__(
        self,
        proposals: object,
        companies: object,
        discovery: object,
        recommendations: object,
        organization: object,
    ) -> None:
        self._proposals, self._companies, self._discovery = (
            proposals,
            companies,
            discovery,
        )
        self._recommendations, self._organization = recommendations, organization

    def build(
        self, proposal_id: int, section_keys: tuple[str, ...]
    ) -> ProposalGenerationContext:
        proposal = self._proposals.get_proposal(proposal_id)
        company = self._companies.get_company(proposal.company_id)
        scan = self._discovery.latest_for_company(company.id)
        eligible_scan = scan if scan and scan.status == "Completed" else None
        recs = tuple(
            r
            for r in self._recommendations.list_recommendations(proposal_id)
            if r.status
            in {RecommendationStatus.APPROVED, RecommendationStatus.ADDED_TO_PROPOSAL}
        )
        items = self._proposals.list_items(proposal_id)
        sections = self._proposals.list_sections(proposal_id)
        references = {f"company:{company.id}", f"organization:{self._organization.id}"}
        if eligible_scan:
            references.add(f"discovery_scan:{eligible_scan.id}")
        references.update(f"recommendation:{r.id}" for r in recs)
        references.update(f"proposal_item:{item.id}" for item in items)
        warnings = (
            () if eligible_scan else ("Completed discovery evidence is unavailable.",)
        )
        return ProposalGenerationContext(
            proposal={
                "id": proposal.id,
                "number": proposal.proposal_number,
                "title": proposal.title,
                "status": proposal.status.value,
                "valid_until": str(proposal.valid_until)
                if proposal.valid_until
                else None,
                "requested_section_keys": section_keys,
            },
            prospect={
                "id": company.id,
                "name": company.name,
                "industry": company.industry,
                "country": company.country,
                "website": company.website,
                "company_size": company.company_size,
                "notes": sanitize_evidence(company.notes or "", 1500),
                "untrusted_discovery_evidence": sanitize_evidence(
                    str(eligible_scan.data), 6000
                )
                if eligible_scan
                else None,
            },
            seller={
                "id": self._organization.id,
                "name": self._organization.display_name,
                "website": self._organization.website,
                "contact_email": self._organization.contact_email,
            },
            recommendations=tuple(
                {
                    "id": r.id,
                    "service_catalog_id": r.service_catalog_id,
                    "reason": r.recommendation_reason,
                    "benefits": r.expected_benefits,
                    "scope": r.suggested_scope,
                    "warnings": r.warnings,
                }
                for r in recs
            ),
            proposal_items=tuple(
                {
                    "id": item.id,
                    "catalog_id": item.service_catalog_id,
                    "title": item.title,
                    "description": item.description,
                    "timeline": item.delivery_timeline,
                    "selection_reason": item.selection_reason,
                }
                for item in items
            ),
            existing_sections=tuple(
                {
                    "id": section.id,
                    "key": section.section_key,
                    "title": section.title,
                    "content": sanitize_evidence(section.content, 6000),
                    "content_source": getattr(section, "content_source", "EMPTY"),
                    "manually_edited": getattr(section, "manually_edited", False),
                }
                for section in sections
            ),
            allowed_source_ids=frozenset(references),
            warnings=warnings,
        )
