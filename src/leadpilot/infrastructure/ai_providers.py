from __future__ import annotations

from leadpilot.application.ai_provider import (
    AIProvider,
    AIProviderError,
    AIProviderTimeout,
    AIRequest,
    AIResponse,
    DisabledAIProvider,
)
from leadpilot.application.ai_schema import *
from leadpilot.config import Settings


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            api_key=settings.ai_api_key,
            timeout=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
        )

    def generate(self, request: AIRequest) -> AIResponse:
        try:
            response = self._client.responses.parse(
                model=request.model,
                instructions=request.system_prompt,
                input=request.evidence_prompt,
                text_format=AIIntelligenceOutput,
                max_output_tokens=request.max_output_tokens,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise AIProviderError(
                    "The provider did not return a usable structured response."
                )
            usage = response.usage
            return AIResponse(
                parsed,
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
                getattr(usage, "total_tokens", None),
                response.id,
            )
        except TimeoutError as exc:
            raise AIProviderTimeout(
                "AI generation timed out. Please try again."
            ) from exc
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(
                "AI generation could not be completed. The deterministic report is still available."
            ) from exc


class FakeAIProvider:
    name = "fake"

    def __init__(self, mode: str = "success") -> None:
        self.mode = mode

    def generate(self, request: AIRequest) -> AIResponse:
        if self.mode == "timeout":
            raise AIProviderTimeout("AI generation timed out.")
        if self.mode == "error":
            raise AIProviderError("The test provider failed.")
        if self.mode == "invalid":
            raise AIProviderError("The provider returned invalid structured output.")
        ref = "website.https"
        output = AIIntelligenceOutput(
            executive_summary="The current website evidence suggests a useful foundation for a discovery conversation.",
            business_profile="The company maintains a publicly observable digital presence; internal capabilities require validation.",
            digital_strengths=[
                Strength(
                    title="Secure website indicator",
                    explanation="HTTPS was assessed in the deterministic scan.",
                    evidence_references=[ref],
                )
            ],
            improvement_areas=[
                Improvement(
                    title="Validate conversion journey",
                    explanation="Public signals provide a starting point.",
                    evidence_references=[ref],
                    business_relevance="A review may clarify enquiry handling.",
                )
            ],
            business_risks=[
                Risk(
                    title="Visibility limitation",
                    explanation="Website evidence cannot verify internal processes.",
                    evidence_references=[ref],
                    risk_level="Low",
                    limitation_note="Validate with the prospect.",
                )
            ],
            quick_wins=[
                QuickWin(
                    title="Review enquiry flow",
                    suggested_action="Map the current public-to-internal handoff.",
                    expected_outcome="A clearer assessment baseline.",
                    estimated_effort="Small",
                    priority="Medium",
                    evidence_references=[ref],
                )
            ],
            strategic_opportunities=[
                Opportunity(
                    opportunity="Digital workflow assessment",
                    business_rationale="Structured evidence supports a discovery discussion.",
                    suggested_outcome="Identify validated improvement options.",
                    recommended_rapidnest_service="Business Process Automation",
                    priority="Medium",
                    evidence_references=[ref],
                )
            ],
            recommended_services=[
                ServiceRecommendation(
                    service="Business Process Automation",
                    rationale="Assess observable-to-internal handoffs.",
                    evidence=[ref],
                    expected_business_outcome="A validated automation roadmap.",
                    priority="Medium",
                    confidence="Medium",
                )
            ],
            implementation_roadmap=[
                RoadmapPhase(
                    phase="Phase 1: Immediate Foundations",
                    objectives=["Validate current workflows"],
                    suggested_initiatives=["Run stakeholder discovery"],
                    estimated_duration_range="1–2 weeks",
                    dependencies=["Prospect validation"],
                    success_indicators=["Agreed baseline"],
                )
            ],
            discovery_questions=[
                DiscoveryQuestion(
                    question="How are website enquiries currently followed up?",
                    why_it_matters="This validates the handoff that public evidence cannot reveal.",
                )
            ],
            outreach_angles=[
                OutreachAngle(
                    subject_or_opening_theme="Digital enquiry journey",
                    personalized_observation="The public website offers observable signals worth validating.",
                    value_proposition="RapidNest can help map practical next steps.",
                    caution_or_assumption="Internal processes are not visible.",
                ),
                OutreachAngle(
                    subject_or_opening_theme="Automation assessment",
                    personalized_observation="The deterministic scan indicates an assessment opportunity.",
                    value_proposition="A short discovery can identify supported priorities.",
                    caution_or_assumption="No internal tooling assumptions are made.",
                ),
            ],
            confidence_notes="Website observations are supported by the cited evidence. Internal processes and priorities require prospect validation.",
        )
        return AIResponse(output, 400, 700, 1100, "fake-response")


def create_ai_provider(settings: Settings) -> AIProvider:
    if not settings.ai_enabled:
        return DisabledAIProvider()
    if settings.ai_provider == "openai":
        return OpenAIProvider(settings)
    if settings.ai_provider == "fake" and settings.environment.lower() in {
        "development",
        "test",
    }:
        return FakeAIProvider()
    raise AIProviderError("The configured AI provider is unavailable.")
