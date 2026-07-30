from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from leadpilot.application.prompt_templates import PromptTemplate
from leadpilot.infrastructure.database.models import PromptTemplateModel


class SqlAlchemyPromptTemplateRepository:
    """Tenant repository that may read platform defaults but writes only overrides."""

    def __init__(
        self, session_factory: Callable[[], Session], organization_id: int
    ) -> None:
        self._session_factory = session_factory
        self.organization_id = organization_id

    def create_version(
        self,
        template_key: str,
        name: str,
        system_template: str,
        user_template: str,
        response_schema_version: str,
        description: str | None,
    ) -> PromptTemplate:
        with self._session_factory() as session, session.begin():
            version = (
                session.scalar(
                    select(func.max(PromptTemplateModel.version)).where(
                        PromptTemplateModel.organization_id == self.organization_id,
                        PromptTemplateModel.template_key == template_key,
                    )
                )
                or 0
            )
            model = PromptTemplateModel(
                organization_id=self.organization_id,
                template_key=template_key,
                version=version + 1,
                name=name,
                description=description,
                system_template=system_template,
                user_template=user_template,
                response_schema_version=response_schema_version,
                is_active=False,
            )
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._template(model)

    def get_active(self, template_key: str) -> PromptTemplate | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(PromptTemplateModel)
                .where(
                    PromptTemplateModel.template_key == template_key,
                    PromptTemplateModel.is_active.is_(True),
                    or_(
                        PromptTemplateModel.organization_id == self.organization_id,
                        PromptTemplateModel.organization_id.is_(None),
                    ),
                )
                .order_by(
                    PromptTemplateModel.organization_id.desc(),
                    PromptTemplateModel.version.desc(),
                )
            )
            return self._template(model) if model else None

    def get_version(self, template_key: str, version: int) -> PromptTemplate | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(PromptTemplateModel)
                .where(
                    PromptTemplateModel.template_key == template_key,
                    PromptTemplateModel.version == version,
                    or_(
                        PromptTemplateModel.organization_id == self.organization_id,
                        PromptTemplateModel.organization_id.is_(None),
                    ),
                )
                .order_by(PromptTemplateModel.organization_id.desc())
            )
            return self._template(model) if model else None

    def list(self) -> tuple[PromptTemplate, ...]:
        with self._session_factory() as session:
            return tuple(
                self._template(model)
                for model in session.scalars(
                    select(PromptTemplateModel)
                    .where(
                        or_(
                            PromptTemplateModel.organization_id == self.organization_id,
                            PromptTemplateModel.organization_id.is_(None),
                        )
                    )
                    .order_by(
                        PromptTemplateModel.template_key,
                        PromptTemplateModel.organization_id.desc(),
                        PromptTemplateModel.version.desc(),
                    )
                )
            )

    def set_active(self, template_id: int, active: bool) -> PromptTemplate | None:
        with self._session_factory() as session, session.begin():
            model = session.scalar(
                select(PromptTemplateModel).where(
                    PromptTemplateModel.id == template_id,
                    PromptTemplateModel.organization_id == self.organization_id,
                )
            )
            if model is None:
                return None
            if active:
                for previous in session.scalars(
                    select(PromptTemplateModel).where(
                        PromptTemplateModel.organization_id == self.organization_id,
                        PromptTemplateModel.template_key == model.template_key,
                        PromptTemplateModel.is_active.is_(True),
                    )
                ):
                    previous.is_active = False
            model.is_active = active
            session.flush()
            session.refresh(model)
            return self._template(model)

    @staticmethod
    def _template(model: PromptTemplateModel) -> PromptTemplate:
        return PromptTemplate(
            model.id,
            model.organization_id,
            model.template_key,
            model.version,
            model.name,
            model.description,
            model.system_template,
            model.user_template,
            model.response_schema_version,
            model.is_active,
            model.updated_at,
        )
