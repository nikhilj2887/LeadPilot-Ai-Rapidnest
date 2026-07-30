from __future__ import annotations

from decimal import Decimal

import pytest

from leadpilot.application.ai_foundation import (
    AIAuthenticationError,
    AIConfigurationError,
    AIIdempotencyConflictError,
    AIInvalidRequestError,
    AIInvalidStructuredResponseError,
    AIOrchestrationService,
    AIProviderConfiguration,
    AIProviderName,
    AIRateLimitError,
    AIRunStatus,
    AIRunType,
    AISchemaValidationError,
    AITimeoutError,
    FakeAIProvider,
    StructuredGenerationRequest,
    estimate_cost,
    render_prompt,
    validate_structured_output,
)

SCHEMA = {
    "type": "object",
    "required": ["summary", "items"],
    "properties": {
        "summary": {"type": "string"},
        "items": {"type": "array"},
    },
}


class MemoryRepository:
    def __init__(self, config=None) -> None:
        self.config = config
        self.runs = {}
        self.by_key = {}
        self.usage = (0, Decimal(0))

    def resolve_configuration(self):
        return self.config

    def usage_current_month(self):
        return self.usage

    def get_idempotent(self, key):
        run_id = self.by_key.get(key)
        if not run_id:
            return None
        run = self.runs[run_id]
        return run_id, run["hash"], run.get("output")

    def create_run(self, request, config, input_hash, snapshot):
        run_id = len(self.runs) + 1
        self.runs[run_id] = {
            "status": AIRunStatus.PENDING,
            "hash": input_hash,
            "snapshot": snapshot,
        }
        if request.idempotency_key:
            self.by_key[request.idempotency_key] = run_id
        return run_id

    def update_run(self, run_id, status, **values):
        self.runs[run_id].update(status=status, **values)


def configuration(max_retries: int = 0):
    return AIProviderConfiguration(
        AIProviderName.FAKE, "fake-model", "Tenant", max_retries=max_retries
    )


def request(**overrides):
    values = {
        "organization_id": 1,
        "user_id": 2,
        "run_type": AIRunType.TEST,
        "system_prompt": "Return JSON.",
        "user_prompt": "Test",
        "response_schema": SCHEMA,
    }
    values.update(overrides)
    return StructuredGenerationRequest(**values)


def test_fake_provider_success_tracks_run_and_idempotency() -> None:
    repository = MemoryRepository(configuration())
    provider = FakeAIProvider()
    service = AIOrchestrationService(repository, {AIProviderName.FAKE: provider})
    result = service.generate_structured(request(idempotency_key="same"))
    assert result.parsed_output["summary"] == "Test response"
    assert result.total_tokens == 30
    assert repository.runs[1]["status"] == AIRunStatus.COMPLETED
    assert service.generate_structured(request(idempotency_key="same")).ai_run_id == 1
    assert provider.calls == 1
    with pytest.raises(AIIdempotencyConflictError):
        service.generate_structured(
            request(idempotency_key="same", user_prompt="Different")
        )


@pytest.mark.parametrize(
    ("mode", "error"),
    (
        ("timeout", AITimeoutError),
        ("rate_limit", AIRateLimitError),
        ("auth", AIAuthenticationError),
        ("invalid_json", AIInvalidStructuredResponseError),
    ),
)
def test_fake_provider_failure_modes(mode, error) -> None:
    repository = MemoryRepository(configuration())
    service = AIOrchestrationService(
        repository, {AIProviderName.FAKE: FakeAIProvider(mode=mode)}
    )
    with pytest.raises(error):
        service.generate_structured(request())
    expected = (
        AIRunStatus.VALIDATION_FAILED if mode == "invalid_json" else AIRunStatus.FAILED
    )
    assert repository.runs[1]["status"] == expected


def test_retry_policy_is_bounded_and_auth_is_not_retried() -> None:
    repository = MemoryRepository(configuration(max_retries=2))
    timeout = FakeAIProvider(mode="timeout")
    service = AIOrchestrationService(
        repository, {AIProviderName.FAKE: timeout}, sleeper=lambda _: None
    )
    with pytest.raises(AITimeoutError):
        service.generate_structured(request())
    assert timeout.calls == 3
    auth = FakeAIProvider(mode="auth")
    with pytest.raises(AIAuthenticationError):
        AIOrchestrationService(
            MemoryRepository(configuration(max_retries=3)),
            {AIProviderName.FAKE: auth},
        ).generate_structured(request())
    assert auth.calls == 1


def test_validation_templates_cost_and_configuration_errors() -> None:
    assert (
        validate_structured_output('{"summary":"ok","items":[]}', SCHEMA)["summary"]
        == "ok"
    )
    with pytest.raises(AISchemaValidationError):
        validate_structured_output('{"summary":"ok"}', SCHEMA)
    assert render_prompt("Hello {name}", {"name": "LeadPilot"}) == "Hello LeadPilot"
    with pytest.raises(AIInvalidRequestError):
        render_prompt("Hello {name}", {})
    assert estimate_cost("unknown", 10, 20) is None
    with pytest.raises(AIConfigurationError):
        AIOrchestrationService(MemoryRepository(), {}).resolve_provider_configuration()
