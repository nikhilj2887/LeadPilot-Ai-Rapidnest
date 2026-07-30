from __future__ import annotations

import hashlib
import json
import string
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol


class AIProviderName(StrEnum):
    GEMINI = "GEMINI"
    OPENAI = "OPENAI"
    ANTHROPIC = "ANTHROPIC"
    AZURE_OPENAI = "AZURE_OPENAI"
    OPENROUTER = "OPENROUTER"
    OLLAMA = "OLLAMA"
    FAKE = "FAKE"


class AIRunType(StrEnum):
    OFFERING_RECOMMENDATION = "OFFERING_RECOMMENDATION"
    PROPOSAL_GENERATION = "PROPOSAL_GENERATION"
    SECTION_GENERATION = "SECTION_GENERATION"
    SECTION_REGENERATION = "SECTION_REGENERATION"
    RESPONSE_REPAIR = "RESPONSE_REPAIR"
    TEST = "TEST"


class AIRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CANCELLED = "CANCELLED"


class AIError(RuntimeError):
    pass


class AIConfigurationError(AIError):
    pass


class AIProviderUnavailableError(AIError):
    pass


class AIAuthenticationError(AIError):
    pass


class AIRateLimitError(AIError):
    pass


class AITimeoutError(AIError):
    pass


class AIUnsupportedModelError(AIError):
    pass


class AIInvalidRequestError(AIError):
    pass


class AIInvalidStructuredResponseError(AIError):
    pass


class AISchemaValidationError(AIError):
    pass


class AIUsageLimitExceededError(AIError):
    pass


class AIIdempotencyConflictError(AIError):
    pass


class AIAuthorizationError(AIError):
    pass


@dataclass(frozen=True, slots=True)
class AIProviderConfiguration:
    provider: AIProviderName
    model_name: str
    source: str
    temperature: Decimal = Decimal("0.1")
    max_output_tokens: int = 2048
    timeout_seconds: int = 60
    max_retries: int = 2
    monthly_token_limit: int | None = None
    monthly_cost_limit: Decimal | None = None
    credentials_reference: str | None = None


@dataclass(frozen=True, slots=True)
class StructuredGenerationRequest:
    organization_id: int
    user_id: int | None
    run_type: AIRunType
    system_prompt: str
    user_prompt: str
    response_schema: dict[str, Any]
    prompt_template_key: str | None = None
    prompt_template_version: int | None = None
    model_name: str | None = None
    temperature: Decimal | None = None
    max_output_tokens: int | None = None
    timeout_seconds: int | None = None
    metadata: dict[str, Any] | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderGenerationResult:
    raw_output: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    provider_request_id: str | None = None
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class StructuredGenerationResult:
    parsed_output: dict[str, Any]
    raw_output: str | None
    provider: AIProviderName
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost: Decimal | None
    finish_reason: str | None
    provider_request_id: str | None
    duration_ms: int
    warnings: tuple[str, ...]
    ai_run_id: int


class StructuredAIProvider(Protocol):
    name: AIProviderName

    def generate_structured(
        self, request: StructuredGenerationRequest, config: AIProviderConfiguration
    ) -> ProviderGenerationResult: ...


class FakeAIProvider:
    name = AIProviderName.FAKE

    def __init__(
        self, response: Mapping[str, Any] | str | None = None, mode: str = "success"
    ) -> None:
        self.response = response or {"summary": "Test response", "items": []}
        self.mode = mode
        self.calls = 0

    def generate_structured(
        self, request: StructuredGenerationRequest, config: AIProviderConfiguration
    ) -> ProviderGenerationResult:
        self.calls += 1
        if self.mode == "timeout":
            raise AITimeoutError("The AI request timed out.")
        if self.mode == "rate_limit":
            raise AIRateLimitError("The AI provider rate limit was reached.")
        if self.mode == "auth":
            raise AIAuthenticationError("AI provider authentication failed.")
        raw = (
            "{invalid"
            if self.mode == "invalid_json"
            else (
                self.response
                if isinstance(self.response, str)
                else json.dumps(self.response)
            )
        )
        return ProviderGenerationResult(raw, 10, 20, 30, "STOP", "fake-request", 5)


class AIRepository(Protocol):
    def resolve_configuration(self) -> AIProviderConfiguration | None: ...
    def usage_current_month(self) -> tuple[int, Decimal]: ...
    def get_idempotent(
        self, key: str
    ) -> tuple[int, str, dict[str, Any] | None] | None: ...
    def create_run(
        self,
        request: StructuredGenerationRequest,
        config: AIProviderConfiguration,
        input_hash: str,
        snapshot: dict[str, Any],
    ) -> int: ...
    def update_run(self, run_id: int, status: AIRunStatus, **values: Any) -> None: ...


class AIOrchestrationService:
    """Provider-neutral structured generation with safe tracking and retries."""

    def __init__(
        self,
        repository: AIRepository,
        providers: Mapping[AIProviderName, StructuredAIProvider],
        *,
        audit: Callable[[str, str, str], None] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._repository = repository
        self._providers = providers
        self._audit = audit
        self._sleeper = sleeper

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        if not request.system_prompt.strip() or not request.user_prompt.strip():
            raise AIInvalidRequestError("System and user prompts are required.")
        config = self.resolve_provider_configuration()
        if request.idempotency_key:
            previous = self._repository.get_idempotent(request.idempotency_key)
            if previous:
                if previous[1] != self._hash(request):
                    raise AIIdempotencyConflictError(
                        "Idempotency key was used for different input."
                    )
                if previous[2] is not None:
                    return self._result(previous[0], previous[2], config)
        self._check_limits(config)
        snapshot = {
            "run_type": request.run_type.value,
            "template_key": request.prompt_template_key,
            "metadata": request.metadata or {},
        }
        input_hash = self._hash(request)
        run_id = self._repository.create_run(request, config, input_hash, snapshot)
        self._repository.update_run(run_id, AIRunStatus.RUNNING)
        self._log("AI_RUN_STARTED", run_id)
        provider = self._providers.get(config.provider)
        if provider is None:
            self._fail(
                run_id, AIConfigurationError("Configured AI provider is unavailable.")
            )
        attempts = 0
        while True:
            try:
                generated = provider.generate_structured(request, config)  # type: ignore[union-attr]
                parsed = validate_structured_output(
                    generated.raw_output, request.response_schema
                )
                estimated = estimate_cost(
                    config.model_name, generated.input_tokens, generated.output_tokens
                )
                self._repository.update_run(
                    run_id,
                    AIRunStatus.COMPLETED,
                    output=parsed,
                    input_tokens=generated.input_tokens,
                    output_tokens=generated.output_tokens,
                    total_tokens=generated.total_tokens,
                    estimated_cost=estimated,
                    duration_ms=generated.duration_ms,
                    provider_request_id=generated.provider_request_id,
                    finish_reason=generated.finish_reason,
                    retry_count=attempts,
                )
                self._log("AI_RUN_COMPLETED", run_id)
                return StructuredGenerationResult(
                    parsed,
                    None,
                    config.provider,
                    config.model_name,
                    generated.input_tokens,
                    generated.output_tokens,
                    generated.total_tokens,
                    estimated,
                    generated.finish_reason,
                    generated.provider_request_id,
                    generated.duration_ms,
                    (),
                    run_id,
                )
            except (
                AITimeoutError,
                AIRateLimitError,
                AIProviderUnavailableError,
            ) as exc:
                if attempts >= config.max_retries:
                    self._fail(run_id, exc, attempts)
                attempts += 1
                self._repository.update_run(
                    run_id, AIRunStatus.RUNNING, retry_count=attempts
                )
                self._log("AI_RUN_RETRIED", run_id)
                self._sleeper(min(2 ** (attempts - 1), 8))
            except (AIInvalidStructuredResponseError, AISchemaValidationError) as exc:
                self._fail(run_id, exc, attempts, AIRunStatus.VALIDATION_FAILED)
            except AIError as exc:
                self._fail(run_id, exc, attempts)

    def resolve_provider_configuration(self) -> AIProviderConfiguration:
        config = self._repository.resolve_configuration()
        if config is None:
            raise AIConfigurationError("AI is not configured for this organization.")
        return config

    def _check_limits(self, config: AIProviderConfiguration) -> None:
        tokens, cost = self._repository.usage_current_month()
        if (
            config.monthly_token_limit is not None
            and tokens >= config.monthly_token_limit
        ):
            raise AIUsageLimitExceededError("Monthly AI token limit has been reached.")
        if config.monthly_cost_limit is not None and cost >= config.monthly_cost_limit:
            raise AIUsageLimitExceededError("Monthly AI cost limit has been reached.")

    def _fail(
        self,
        run_id: int,
        error: AIError,
        retries: int = 0,
        status: AIRunStatus = AIRunStatus.FAILED,
    ) -> None:
        self._repository.update_run(
            run_id,
            status,
            error_code=type(error).__name__,
            error_message=str(error)[:500],
            retry_count=retries,
        )
        self._log("AI_RUN_FAILED", run_id)
        raise error

    def _log(self, action: str, run_id: int) -> None:
        if self._audit:
            self._audit(action, "ai_run", str(run_id))

    @staticmethod
    def _hash(request: StructuredGenerationRequest) -> str:
        safe = json.dumps(
            {
                "run_type": request.run_type,
                "system": request.system_prompt,
                "user": request.user_prompt,
                "schema": request.response_schema,
                "metadata": request.metadata,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(safe.encode()).hexdigest()

    @staticmethod
    def _result(
        run_id: int, output: dict[str, Any], config: AIProviderConfiguration
    ) -> StructuredGenerationResult:
        return StructuredGenerationResult(
            output,
            None,
            config.provider,
            config.model_name,
            None,
            None,
            None,
            None,
            None,
            None,
            0,
            ("Reused idempotent result.",),
            run_id,
        )


def validate_structured_output(raw: str, schema: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIInvalidStructuredResponseError(
            "AI provider returned invalid JSON."
        ) from exc
    if not isinstance(value, dict):
        raise AISchemaValidationError("Structured output must be a JSON object.")
    required = schema.get("required", [])
    missing = [key for key in required if key not in value]
    if missing:
        raise AISchemaValidationError(
            f"Structured output is missing: {', '.join(missing)}"
        )
    properties = schema.get("properties", {})
    types = {
        "string": str,
        "array": list,
        "object": dict,
        "integer": int,
        "number": (int, float),
    }
    for key, definition in properties.items():
        expected = types.get(definition.get("type"))
        if key in value and expected and not isinstance(value[key], expected):
            raise AISchemaValidationError(
                f"Structured output field '{key}' has an invalid type."
            )
    return value


MODEL_COSTS: dict[str, tuple[Decimal, Decimal]] = {}


def estimate_cost(
    model: str, input_tokens: int | None, output_tokens: int | None
) -> Decimal | None:
    pricing = MODEL_COSTS.get(model)
    if pricing is None or input_tokens is None or output_tokens is None:
        return None
    return (
        (Decimal(input_tokens) * pricing[0] + Decimal(output_tokens) * pricing[1])
        / Decimal(1_000_000)
    ).quantize(Decimal("0.000001"))


def render_prompt(template: str, variables: Mapping[str, Any]) -> str:
    required = {name for _, name, _, _ in string.Formatter().parse(template) if name}
    missing = required - variables.keys()
    if missing:
        raise AIInvalidRequestError(
            f"Missing template variables: {', '.join(sorted(missing))}"
        )
    return template.format_map(dict(variables))
