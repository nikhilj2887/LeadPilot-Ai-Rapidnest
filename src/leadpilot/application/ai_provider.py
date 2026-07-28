from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from leadpilot.application.ai_schema import AIIntelligenceOutput


class AIProviderError(RuntimeError):
    pass


class AIProviderDisabled(AIProviderError):
    pass


class AIProviderTimeout(AIProviderError):
    pass


@dataclass(frozen=True, slots=True)
class AIRequest:
    system_prompt: str
    evidence_prompt: str
    model: str
    temperature: float
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class AIResponse:
    output: AIIntelligenceOutput
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    response_id: str | None = None


class AIProvider(Protocol):
    name: str

    def generate(self, request: AIRequest) -> AIResponse: ...


class DisabledAIProvider:
    name = "disabled"

    def generate(self, request: AIRequest) -> AIResponse:
        raise AIProviderDisabled(
            "AI Intelligence is not configured. Add an API key and enable AI to generate a draft."
        )
