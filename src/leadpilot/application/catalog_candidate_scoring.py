from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProspectEvidence:
    organization_id: int
    company_id: int
    company_name: str
    industry: str | None
    country: str | None
    website_url: str | None
    company_size: str | None = None
    company_notes: str | None = None
    discovery_scan_id: int | None = None
    discovery_summary: str = ""
    observed_capabilities: tuple[str, ...] = ()
    observed_gaps: tuple[str, ...] = ()
    business_opportunities: tuple[str, ...] = ()
    website_findings: tuple[str, ...] = ()
    digital_maturity_score: int | None = None
    ai_readiness_score: int | None = None
    automation_potential_score: int | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    industry: int = 0
    problem: int = 0
    tags: int = 0
    findings: int = 0
    existing_recommendation: int = 0
    readiness: int = 0

    @property
    def total(self) -> int:
        return min(
            100,
            sum(
                (
                    self.industry,
                    self.problem,
                    self.tags,
                    self.findings,
                    self.existing_recommendation,
                    self.readiness,
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class CatalogCandidate:
    service_catalog_id: int
    name: str
    description: str
    category: str
    pricing_type: str
    base_price: Decimal | None
    currency: str
    timeline: str | None
    industries: tuple[str, ...]
    tags: tuple[str, ...]
    problems: tuple[str, ...]
    benefits: tuple[str, ...]
    deliverables: tuple[str, ...]
    deterministic_score: int
    score_breakdown: ScoreBreakdown


def sanitize_evidence(value: str, limit: int = 4000) -> str:
    clean = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(
        r"(?i)(ignore previous instructions|return all catalog items|change service id)",
        "[untrusted instruction removed]",
        clean,
    )
    return re.sub(r"\s+", " ", clean).strip()[:limit]


def score_candidate(evidence: ProspectEvidence, offering: object) -> CatalogCandidate:
    tokens = lambda text: set(re.findall(r"[a-z0-9]+", (text or "").casefold()))
    evidence_text = " ".join(
        (
            *evidence.observed_gaps,
            *evidence.business_opportunities,
            *evidence.website_findings,
            evidence.discovery_summary,
            evidence.company_notes or "",
        )
    )
    evidence_tokens = tokens(evidence_text)
    industries = tuple(getattr(offering, "target_industries", ()))
    tags = tuple(getattr(offering, "tags", ()))
    problems = tuple(getattr(offering, "problems_solved", ()))
    benefits = tuple(getattr(offering, "business_benefits", ()))
    description = getattr(offering, "detailed_description", None) or getattr(
        offering, "short_description", ""
    )
    industry = (
        20
        if evidence.industry
        and evidence.industry.casefold() in {item.casefold() for item in industries}
        else 0
    )
    problem = min(20, 5 * len(evidence_tokens & tokens(" ".join(problems))))
    tag_score = min(15, 5 * len(evidence_tokens & tokens(" ".join(tags))))
    findings = min(
        20,
        4
        * len(
            evidence_tokens & tokens(f"{description} {getattr(offering, 'name', '')}")
        ),
    )
    existing = (
        15
        if getattr(offering, "name", "").casefold() in evidence_text.casefold()
        else 0
    )
    readiness = (
        10
        if max(
            evidence.ai_readiness_score or 0, evidence.automation_potential_score or 0
        )
        >= 60
        and tokens("ai automation") & tokens(f"{' '.join(tags)} {description}")
        else 0
    )
    breakdown = ScoreBreakdown(
        industry, problem, tag_score, findings, existing, readiness
    )
    return CatalogCandidate(
        offering.id,
        offering.name,
        description,
        offering.category,
        str(offering.pricing_model),
        offering.base_price,
        offering.currency,
        offering.estimated_timeline,
        industries,
        tags,
        problems,
        benefits,
        tuple(getattr(offering, "deliverables", ())),
        breakdown.total,
        breakdown,
    )


def select_candidates(
    evidence: ProspectEvidence,
    offerings: tuple[object, ...],
    *,
    limit: int = 15,
    minimum_score: int = 20,
) -> tuple[CatalogCandidate, ...]:
    scored = (
        score_candidate(evidence, offering)
        for offering in offerings
        if getattr(offering, "is_active", False)
    )
    return tuple(
        sorted(
            (item for item in scored if item.deterministic_score >= minimum_score),
            key=lambda item: (-item.deterministic_score, item.service_catalog_id),
        )[:limit]
    )
