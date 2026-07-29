from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadpilot.application.organizations import (
    OrganizationBranding,
    OrganizationCreate,
    OrganizationDetails,
    OrganizationService,
    OrganizationSummary,
    OrganizationUpdate,
    validate_color,
    validate_logo_reference,
)
from leadpilot.infrastructure.database.models import (
    OrganizationBrandingModel,
    OrganizationModel,
    OrganizationServiceModel,
)


class OrganizationRepository:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        audit: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit = audit

    def create(self, values: OrganizationCreate) -> OrganizationDetails:
        with self._session_factory() as session, session.begin():
            model = OrganizationModel(**values.model_dump())
            session.add(model)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ValueError("Organization slug already exists") from exc
            session.refresh(model)
            result = self._details(model)
        if self._audit:
            self._audit("CREATE_ORGANIZATION", "organization", str(result.id))
        return result

    def get(self, organization_id: int) -> OrganizationDetails | None:
        with self._session_factory() as session:
            model = session.get(OrganizationModel, organization_id)
            return self._details(model) if model else None

    def get_by_slug(self, slug: str) -> OrganizationDetails | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(OrganizationModel).where(OrganizationModel.slug == slug)
            )
            return self._details(model) if model else None

    def list_active(self) -> list[OrganizationSummary]:
        with self._session_factory() as session:
            models = session.scalars(
                select(OrganizationModel)
                .where(OrganizationModel.status == "active")
                .order_by(OrganizationModel.display_name)
            )
            return [OrganizationSummary.model_validate(model) for model in models]

    def list_all(self) -> list[OrganizationSummary]:
        with self._session_factory() as session:
            models = session.scalars(
                select(OrganizationModel).order_by(OrganizationModel.display_name)
            )
            return [OrganizationSummary.model_validate(model) for model in models]

    def update(
        self, organization_id: int, values: OrganizationUpdate
    ) -> OrganizationDetails | None:
        with self._session_factory() as session, session.begin():
            model = session.get(OrganizationModel, organization_id)
            if model is None:
                return None
            for key, value in values.model_dump(exclude_unset=True).items():
                setattr(model, key, value)
            session.flush()
            session.refresh(model)
            result = self._details(model)
        if self._audit:
            self._audit("UPDATE_ORGANIZATION", "organization", str(organization_id))
        return result

    def get_branding(self, organization_id: int) -> OrganizationBranding | None:
        with self._session_factory() as session:
            model = session.get(OrganizationBrandingModel, organization_id)
            return self._branding(model) if model else None

    def update_branding(
        self, organization_id: int, values: dict[str, Any]
    ) -> OrganizationBranding:
        clean = dict(values)
        for field in ("primary_color", "secondary_color", "accent_color"):
            if field in clean:
                clean[field] = validate_color(clean[field])
        if "logo_reference" in clean:
            clean["logo_reference"] = validate_logo_reference(clean["logo_reference"])
        with self._session_factory() as session, session.begin():
            model = session.get(OrganizationBrandingModel, organization_id)
            if model is None:
                model = OrganizationBrandingModel(
                    organization_id=organization_id,
                    brand_name=clean.pop("brand_name", "LeadPilot AI"),
                    **clean,
                )
                session.add(model)
            else:
                for key, value in clean.items():
                    setattr(model, key, value)
            session.flush()
            session.refresh(model)
            return self._branding(model)

    def list_services(
        self, organization_id: int, *, active_only: bool = False
    ) -> list[OrganizationService]:
        statement = select(OrganizationServiceModel).where(
            OrganizationServiceModel.organization_id == organization_id
        )
        if active_only:
            statement = statement.where(OrganizationServiceModel.is_active.is_(True))
        statement = statement.order_by(
            OrganizationServiceModel.display_order, OrganizationServiceModel.name
        )
        with self._session_factory() as session:
            return [self._service(x) for x in session.scalars(statement)]

    def create_service(
        self, organization_id: int, **values: Any
    ) -> OrganizationService:
        with self._session_factory() as session, session.begin():
            model = OrganizationServiceModel(organization_id=organization_id, **values)
            session.add(model)
            session.flush()
            session.refresh(model)
            return self._service(model)

    def update_service(
        self, organization_id: int, service_id: int, **values: Any
    ) -> OrganizationService | None:
        with self._session_factory() as session, session.begin():
            model = session.scalar(
                select(OrganizationServiceModel).where(
                    OrganizationServiceModel.id == service_id,
                    OrganizationServiceModel.organization_id == organization_id,
                )
            )
            if model is None:
                return None
            for key, value in values.items():
                setattr(model, key, value)
            session.flush()
            session.refresh(model)
            return self._service(model)

    @staticmethod
    def _details(model: OrganizationModel) -> OrganizationDetails:
        return OrganizationDetails.model_validate(model)

    @staticmethod
    def _branding(model: OrganizationBrandingModel) -> OrganizationBranding:
        return OrganizationBranding(
            **{
                column.name: getattr(model, column.name)
                for column in model.__table__.columns
            }
        )

    @staticmethod
    def _service(model: OrganizationServiceModel) -> OrganizationService:
        return OrganizationService(
            **{
                column.name: getattr(model, column.name)
                for column in model.__table__.columns
            }
        )
