from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from leadpilot.application.ai_foundation import (
    AIProviderConfiguration,
    AIProviderName,
    AIRunStatus,
    StructuredGenerationRequest,
)
from leadpilot.infrastructure.database.models import AIProviderConfigModel, AIRunModel


class AIFoundationRepository:
    """Tenant-bound AI configuration and run persistence."""

    def __init__(
        self, session_factory: Callable[[], Session], organization_id: int
    ) -> None:
        self._session_factory = session_factory
        self.organization_id = organization_id

    def resolve_configuration(self) -> AIProviderConfiguration | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(AIProviderConfigModel)
                .where(
                    AIProviderConfigModel.is_active.is_(True),
                    AIProviderConfigModel.is_default.is_(True),
                    or_(
                        AIProviderConfigModel.organization_id == self.organization_id,
                        AIProviderConfigModel.organization_id.is_(None),
                    ),
                )
                .order_by(AIProviderConfigModel.organization_id.desc())
            )
            if model:
                return self._configuration(
                    model, "Tenant" if model.organization_id else "Platform"
                )
        provider = os.getenv("LEADPILOT_AI_PROVIDER", "").strip().upper()
        model_name = os.getenv("LEADPILOT_AI_MODEL", "").strip()
        credential = (
            "GEMINI_API_KEY" if provider == "GEMINI" else "LEADPILOT_AI_API_KEY"
        )
        if provider and model_name and os.getenv(credential, "").strip():
            return AIProviderConfiguration(
                provider=AIProviderName(provider),
                model_name=model_name,
                source="Environment",
                max_output_tokens=int(
                    os.getenv("LEADPILOT_AI_MAX_OUTPUT_TOKENS", "2048")
                ),
                timeout_seconds=int(os.getenv("LEADPILOT_AI_TIMEOUT_SECONDS", "60")),
                credentials_reference=credential,
            )
        return None

    def usage_current_month(self) -> tuple[int, Decimal]:
        month = datetime.now(UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        with self._session_factory() as session:
            tokens, cost = session.execute(
                select(
                    func.coalesce(func.sum(AIRunModel.total_tokens), 0),
                    func.coalesce(func.sum(AIRunModel.estimated_cost), 0),
                ).where(
                    AIRunModel.organization_id == self.organization_id,
                    AIRunModel.status == AIRunStatus.COMPLETED.value,
                    AIRunModel.created_at >= month,
                )
            ).one()
        return int(tokens), Decimal(cost)

    def get_idempotent(self, key: str) -> tuple[int, str, dict[str, Any] | None] | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(AIRunModel).where(
                    AIRunModel.organization_id == self.organization_id,
                    AIRunModel.idempotency_key == key,
                )
            )
            if model is None:
                return None
            return (
                model.id,
                model.input_hash,
                json.loads(model.output_json) if model.output_json else None,
            )

    def create_run(
        self,
        request: StructuredGenerationRequest,
        config: AIProviderConfiguration,
        input_hash: str,
        snapshot: dict[str, Any],
    ) -> int:
        with self._session_factory() as session, session.begin():
            model = AIRunModel(
                organization_id=self.organization_id,
                user_id=request.user_id,
                run_type=request.run_type.value,
                provider=config.provider.value,
                model_name=request.model_name or config.model_name,
                status=AIRunStatus.PENDING.value,
                prompt_template_key=request.prompt_template_key,
                prompt_template_version=request.prompt_template_version,
                idempotency_key=request.idempotency_key,
                input_hash=input_hash,
                input_snapshot_json=json.dumps(snapshot, sort_keys=True),
                started_at=datetime.now(UTC),
            )
            session.add(model)
            session.flush()
            return model.id

    def update_run(self, run_id: int, status: AIRunStatus, **values: Any) -> None:
        with self._session_factory() as session, session.begin():
            model = session.scalar(
                select(AIRunModel).where(
                    AIRunModel.id == run_id,
                    AIRunModel.organization_id == self.organization_id,
                )
            )
            if model is None:
                return
            model.status = status.value
            aliases = {"output": "output_json"}
            for key, value in values.items():
                field = aliases.get(key, key)
                setattr(
                    model,
                    field,
                    json.dumps(value, sort_keys=True) if key == "output" else value,
                )
            if status in {
                AIRunStatus.COMPLETED,
                AIRunStatus.FAILED,
                AIRunStatus.VALIDATION_FAILED,
            }:
                model.completed_at = datetime.now(UTC)

    @staticmethod
    def _configuration(
        model: AIProviderConfigModel, source: str
    ) -> AIProviderConfiguration:
        return AIProviderConfiguration(
            AIProviderName(model.provider),
            model.model_name,
            source,
            model.temperature,
            model.max_output_tokens,
            model.request_timeout_seconds,
            model.max_retries,
            model.monthly_token_limit,
            model.monthly_cost_limit,
            model.credentials_reference,
        )
