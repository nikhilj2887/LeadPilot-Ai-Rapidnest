from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Priority = Literal["Low", "Medium", "High"]
Effort = Literal["Small", "Medium", "Large"]
Confidence = Literal["Low", "Medium", "High"]
SERVICES = (
    "AI Chatbots",
    "WhatsApp Automation",
    "CRM Integration",
    "Business Process Automation",
    "Appointment Automation",
    "ERP Solutions",
    "Website Modernization",
    "Mobile Applications",
    "Cloud and Digital Transformation",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Strength(StrictModel):
    title: str = Field(max_length=160)
    explanation: str = Field(max_length=1000)
    evidence_references: list[str] = Field(max_length=12)


class Improvement(Strength):
    business_relevance: str = Field(max_length=1000)


class Risk(Strength):
    risk_level: Priority
    limitation_note: str = Field(max_length=600)


class QuickWin(StrictModel):
    title: str = Field(max_length=160)
    suggested_action: str = Field(max_length=1000)
    expected_outcome: str = Field(max_length=800)
    estimated_effort: Effort
    priority: Priority
    evidence_references: list[str] = Field(max_length=12)


class Opportunity(StrictModel):
    opportunity: str = Field(max_length=200)
    business_rationale: str = Field(max_length=1000)
    suggested_outcome: str = Field(max_length=800)
    recommended_rapidnest_service: str = Field(max_length=100)
    priority: Priority
    evidence_references: list[str] = Field(max_length=12)


class ServiceRecommendation(StrictModel):
    service: Literal[*SERVICES]
    rationale: str = Field(max_length=1000)
    evidence: list[str] = Field(max_length=12)
    expected_business_outcome: str = Field(max_length=800)
    priority: Priority
    confidence: Confidence


class RoadmapPhase(StrictModel):
    phase: Literal[
        "Phase 1: Immediate Foundations",
        "Phase 2: Automation and Integration",
        "Phase 3: Scale and Optimization",
    ]
    objectives: list[str] = Field(max_length=8)
    suggested_initiatives: list[str] = Field(max_length=8)
    estimated_duration_range: str = Field(max_length=60)
    dependencies: list[str] = Field(max_length=8)
    success_indicators: list[str] = Field(max_length=8)


class DiscoveryQuestion(StrictModel):
    question: str = Field(max_length=500)
    why_it_matters: str = Field(max_length=700)


class OutreachAngle(StrictModel):
    subject_or_opening_theme: str = Field(max_length=200)
    personalized_observation: str = Field(max_length=700)
    value_proposition: str = Field(max_length=700)
    caution_or_assumption: str = Field(max_length=500)


class AIIntelligenceOutput(StrictModel):
    executive_summary: str = Field(min_length=1, max_length=1800)
    business_profile: str = Field(min_length=1, max_length=1800)
    digital_strengths: list[Strength] = Field(max_length=12)
    improvement_areas: list[Improvement] = Field(max_length=12)
    business_risks: list[Risk] = Field(max_length=10)
    quick_wins: list[QuickWin] = Field(max_length=10)
    strategic_opportunities: list[Opportunity] = Field(max_length=10)
    recommended_services: list[ServiceRecommendation] = Field(max_length=9)
    implementation_roadmap: list[RoadmapPhase] = Field(max_length=3)
    discovery_questions: list[DiscoveryQuestion] = Field(max_length=15)
    outreach_angles: list[OutreachAngle] = Field(min_length=2, max_length=3)
    confidence_notes: str = Field(min_length=1, max_length=1800)
