from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Any, Protocol

from leadpilot.application.ai_evidence import (
    build_snapshot,
    evidence_references,
    snapshot_hash,
)
from leadpilot.application.ai_prompt import PROMPT_VERSION, SCHEMA_VERSION, build_prompt
from leadpilot.application.ai_provider import AIProvider, AIProviderError, AIRequest

AI_STATUSES = ("Pending", "Running", "Completed", "Failed")
REVIEW_STATUSES = ("Unreviewed", "Reviewed", "Needs Changes")


class DiscoveryAIError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DiscoveryAIAnalysis:
    id: int
    discovery_scan_id: int
    company_id: int
    status: str
    review_status: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    generated_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    input_snapshot_hash: str
    data: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None
    reviewer_notes: str | None = None
    organization_id: int = 1

    def __getattr__(self, name: str) -> Any:
        if name in self.data:
            return self.data[name]
        raise AttributeError(name)


class AIAnalysisRepository(Protocol):
    def create(self, **values: Any) -> DiscoveryAIAnalysis: ...
    def update_status(self, analysis_id: int, status: str) -> DiscoveryAIAnalysis: ...
    def save_completed(
        self, analysis_id: int, **values: Any
    ) -> DiscoveryAIAnalysis: ...
    def save_failed(self, analysis_id: int, message: str) -> DiscoveryAIAnalysis: ...
    def get_by_id(self, analysis_id: int) -> DiscoveryAIAnalysis | None: ...
    def get_latest_by_scan(self, scan_id: int) -> DiscoveryAIAnalysis | None: ...
    def get_latest_by_company(self, company_id: int) -> DiscoveryAIAnalysis | None: ...
    def list_by_scan(self, scan_id: int) -> list[DiscoveryAIAnalysis]: ...
    def list_by_company(self, company_id: int) -> list[DiscoveryAIAnalysis]: ...
    def update_review(
        self, analysis_id: int, status: str, notes: str | None
    ) -> DiscoveryAIAnalysis: ...
    def dashboard_summary(self) -> dict[str, Any]: ...


class DiscoveryAIService:
    def __init__(
        self,
        repository: AIAnalysisRepository,
        companies: Any,
        discovery: Any,
        provider: AIProvider,
        settings: Any,
        organizations: Any | None = None,
        organization_id: int = 1,
    ) -> None:
        self._repository, self._companies, self._discovery = (
            repository,
            companies,
            discovery,
        )
        self._provider, self._settings = provider, settings
        self._organizations = organizations
        self._organization_id = organization_id

    @property
    def availability(self) -> tuple[bool, str]:
        if not self._settings.ai_enabled:
            return (
                False,
                "AI Intelligence is disabled until an API key is configured and AI is enabled.",
            )
        return True, f"{self._settings.ai_provider} · {self._settings.ai_model}"

    def generate(
        self, scan_id: int, *, regenerate: bool = False
    ) -> DiscoveryAIAnalysis:
        scan = self._discovery.get_scan(scan_id)
        if scan.status != "Completed":
            raise DiscoveryAIError(
                "AI Intelligence requires a completed Discovery Scan."
            )
        company = self._companies.get_company(scan.company_id)
        snapshot = build_snapshot(company, scan)
        digest = snapshot_hash(snapshot)
        latest = self._repository.get_latest_by_scan(scan.id)
        if latest and latest.status in {"Pending", "Running"}:
            raise DiscoveryAIError("AI Intelligence generation is already in progress.")
        if (
            latest
            and latest.status == "Completed"
            and latest.input_snapshot_hash == digest
            and not regenerate
        ):
            raise DiscoveryAIError(
                "A current AI analysis already exists. Choose Regenerate to create a new version."
            )
        record = self._repository.create(
            discovery_scan_id=scan.id,
            company_id=company.id,
            provider=self._provider.name,
            model=self._settings.ai_model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            input_snapshot_hash=digest,
        )
        self._repository.update_status(record.id, "Running")
        started = monotonic()
        try:
            organization_profile = None
            if self._organizations is not None:
                organization = self._organizations.get(self._organization_id)
                branding = self._organizations.get_branding(self._organization_id)
                services = self._organizations.list_services(
                    self._organization_id, active_only=True
                )
                organization_profile = {
                    "display_name": organization.display_name,
                    "brand_name": branding.brand_name
                    if branding
                    else organization.display_name,
                    "website": organization.website,
                    "contact_email": organization.contact_email,
                    "contact_phone": organization.contact_phone,
                    "services": [
                        {
                            "name": item.name,
                            "description": item.short_description,
                        }
                        for item in services
                    ],
                }
            system, evidence = build_prompt(snapshot, organization_profile)
            response = self._provider.generate(
                AIRequest(
                    system,
                    evidence,
                    self._settings.ai_model,
                    self._settings.ai_temperature,
                    self._settings.ai_max_output_tokens,
                )
            )
            known = set(snapshot["evidence_catalogue"])
            refs = evidence_references(response.output)
            unknown = refs - known
            if unknown:
                raise DiscoveryAIError(
                    "The AI response cited evidence that was not present in the scan."
                )
            cost = calculate_cost(
                response.input_tokens,
                response.output_tokens,
                self._settings.ai_input_price_per_million,
                self._settings.ai_output_price_per_million,
            )
            values = response.output.model_dump()
            return self._repository.save_completed(
                record.id,
                **values,
                evidence_references=sorted(refs),
                input_token_count=response.input_tokens,
                output_token_count=response.output_tokens,
                total_token_count=response.total_tokens,
                estimated_cost=cost,
                latency_ms=round((monotonic() - started) * 1000),
                raw_response_metadata={"response_id": response.response_id}
                if response.response_id
                else {},
            )
        except (AIProviderError, DiscoveryAIError) as exc:
            self._repository.save_failed(record.id, str(exc))
            raise DiscoveryAIError(str(exc)) from exc
        except Exception as exc:
            self._repository.save_failed(
                record.id, "AI Intelligence could not be generated safely."
            )
            raise DiscoveryAIError(
                "AI Intelligence could not be generated safely."
            ) from exc

    def get(self, analysis_id: int) -> DiscoveryAIAnalysis:
        result = self._repository.get_by_id(analysis_id)
        if result is None:
            raise DiscoveryAIError("That AI analysis is no longer available.")
        return result

    def latest_for_scan(self, scan_id: int) -> DiscoveryAIAnalysis | None:
        return self._repository.get_latest_by_scan(scan_id)

    def latest_for_company(self, company_id: int) -> DiscoveryAIAnalysis | None:
        return self._repository.get_latest_by_company(company_id)

    def history_for_scan(self, scan_id: int) -> list[DiscoveryAIAnalysis]:
        return self._repository.list_by_scan(scan_id)

    def is_current(self, analysis: DiscoveryAIAnalysis) -> bool:
        scan = self._discovery.get_scan(analysis.discovery_scan_id)
        company = self._companies.get_company(analysis.company_id)
        return analysis.input_snapshot_hash == snapshot_hash(
            build_snapshot(company, scan)
        )

    def update_review(
        self, analysis_id: int, status: str, notes: str | None = None
    ) -> DiscoveryAIAnalysis:
        if status not in REVIEW_STATUSES:
            raise DiscoveryAIError("Invalid review status.")
        return self._repository.update_review(analysis_id, status, notes)

    def dashboard_summary(self) -> dict[str, Any]:
        return self._repository.dashboard_summary()


def calculate_cost(
    input_tokens: int | None,
    output_tokens: int | None,
    input_rate: float | None,
    output_rate: float | None,
) -> float | None:
    if None in (input_tokens, output_tokens, input_rate, output_rate):
        return None
    return round(
        (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 6
    )
