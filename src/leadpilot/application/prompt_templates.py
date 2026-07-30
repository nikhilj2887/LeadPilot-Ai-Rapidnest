from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from leadpilot.application.ai_foundation import AIInvalidRequestError, render_prompt


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    id: int
    organization_id: int | None
    template_key: str
    version: int
    name: str
    description: str | None
    system_template: str
    user_template: str
    response_schema_version: str
    is_active: bool
    updated_at: datetime


class PromptTemplateRepository(Protocol):
    def create_version(
        self,
        template_key: str,
        name: str,
        system_template: str,
        user_template: str,
        response_schema_version: str,
        description: str | None,
    ) -> PromptTemplate: ...
    def get_active(self, template_key: str) -> PromptTemplate | None: ...
    def get_version(self, template_key: str, version: int) -> PromptTemplate | None: ...
    def list(self) -> tuple[PromptTemplate, ...]: ...
    def set_active(self, template_id: int, active: bool) -> PromptTemplate | None: ...


class PromptTemplateService:
    """Version-preserving tenant prompt management with safe substitution."""

    def __init__(self, repository: PromptTemplateRepository) -> None:
        self._repository = repository

    def create_template_version(
        self,
        template_key: str,
        name: str,
        system_template: str,
        user_template: str,
        response_schema_version: str,
        description: str | None = None,
    ) -> PromptTemplate:
        if not template_key.strip() or not name.strip():
            raise AIInvalidRequestError("Template key and name are required.")
        return self._repository.create_version(
            template_key.strip(),
            name.strip(),
            system_template,
            user_template,
            response_schema_version,
            description,
        )

    def get_active_template(self, template_key: str) -> PromptTemplate:
        template = self._repository.get_active(template_key)
        if template is None:
            raise AIInvalidRequestError(
                f"No active template exists for '{template_key}'."
            )
        return template

    def get_template_version(self, template_key: str, version: int) -> PromptTemplate:
        template = self._repository.get_version(template_key, version)
        if template is None:
            raise AIInvalidRequestError("Prompt template version was not found.")
        return template

    def list_templates(self) -> tuple[PromptTemplate, ...]:
        return self._repository.list()

    def activate_version(self, template_id: int) -> PromptTemplate:
        template = self._repository.set_active(template_id, True)
        if template is None:
            raise AIInvalidRequestError("Prompt template was not found.")
        return template

    def deactivate_version(self, template_id: int) -> PromptTemplate:
        template = self._repository.set_active(template_id, False)
        if template is None:
            raise AIInvalidRequestError("Prompt template was not found.")
        return template

    def render_template(
        self, template_key: str, variables: dict[str, object]
    ) -> tuple[str, str, PromptTemplate]:
        template = self.get_active_template(template_key)
        return (
            render_prompt(template.system_template, variables),
            render_prompt(template.user_template, variables),
            template,
        )
