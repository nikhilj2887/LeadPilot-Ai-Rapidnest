from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from leadpilot.application.companies import Company
from leadpilot.infrastructure.database.models import CompanyModel, OrganizationModel


class CompanyRepository:
    """SQLAlchemy-backed persistence operations for companies."""

    def __init__(
        self, session_factory: Callable[[], Session], organization_id: int = 1
    ) -> None:
        self._session_factory = session_factory
        self.organization_id = organization_id

    def create(self, values: dict[str, str | None]) -> Company:
        with self._session_factory() as session, session.begin():
            self._ensure_development_default(session)
            company = CompanyModel(organization_id=self.organization_id, **values)
            session.add(company)
            session.flush()
            session.refresh(company)
            session.expunge(company)
            return self._to_company(company)

    def get_by_id(self, company_id: int) -> Company | None:
        with self._session_factory() as session:
            company = session.scalar(
                select(CompanyModel).where(
                    CompanyModel.id == company_id,
                    CompanyModel.organization_id == self.organization_id,
                )
            )
            return self._to_company(company) if company else None

    def get_by_name(self, name: str) -> Company | None:
        with self._session_factory() as session:
            company = session.scalar(
                select(CompanyModel).where(
                    func.lower(CompanyModel.name) == name.casefold(),
                    CompanyModel.organization_id == self.organization_id,
                )
            )
            return self._to_company(company) if company else None

    def list_all(self) -> list[Company]:
        with self._session_factory() as session:
            models = session.scalars(
                select(CompanyModel)
                .where(CompanyModel.organization_id == self.organization_id)
                .order_by(CompanyModel.name)
            )
            return [self._to_company(model) for model in models]

    def search(self, query: str) -> list[Company]:
        pattern = f"%{query.strip().casefold()}%"
        fields = (
            CompanyModel.name,
            CompanyModel.website,
            CompanyModel.industry,
            CompanyModel.country,
            CompanyModel.city,
        )
        with self._session_factory() as session:
            statement = (
                select(CompanyModel)
                .where(
                    CompanyModel.organization_id == self.organization_id,
                    or_(*(func.lower(field).like(pattern) for field in fields)),
                )
                .order_by(CompanyModel.name)
            )
            return [self._to_company(model) for model in session.scalars(statement)]

    def count(self) -> int:
        with self._session_factory() as session:
            return (
                session.scalar(
                    select(func.count(CompanyModel.id)).where(
                        CompanyModel.organization_id == self.organization_id
                    )
                )
                or 0
            )

    def update(self, company_id: int, values: dict[str, str | None]) -> Company | None:
        with self._session_factory() as session, session.begin():
            company = session.scalar(
                select(CompanyModel).where(
                    CompanyModel.id == company_id,
                    CompanyModel.organization_id == self.organization_id,
                )
            )
            if company is None:
                return None
            for field, value in values.items():
                setattr(company, field, value)
            session.flush()
            session.refresh(company)
            session.expunge(company)
            return self._to_company(company)

    def delete(self, company_id: int) -> bool:
        with self._session_factory() as session, session.begin():
            company = session.scalar(
                select(CompanyModel).where(
                    CompanyModel.id == company_id,
                    CompanyModel.organization_id == self.organization_id,
                )
            )
            if company is None:
                return False
            session.delete(company)
            return True

    def count_by_status(self) -> dict[str, int]:
        return self._grouped_counts(CompanyModel.status)

    def count_by_country(self) -> dict[str, int]:
        return self._grouped_counts(CompanyModel.country)

    def count_by_industry(self) -> dict[str, int]:
        return self._grouped_counts(CompanyModel.industry)

    def list_recent(self, limit: int = 5) -> list[Company]:
        with self._session_factory() as session:
            statement = (
                select(CompanyModel)
                .where(CompanyModel.organization_id == self.organization_id)
                .order_by(CompanyModel.created_at.desc(), CompanyModel.id.desc())
                .limit(limit)
            )
            return [self._to_company(model) for model in session.scalars(statement)]

    def _grouped_counts(self, field: object) -> dict[str, int]:
        with self._session_factory() as session:
            rows = session.execute(
                select(field, func.count(CompanyModel.id))
                .where(
                    CompanyModel.organization_id == self.organization_id,
                    field.is_not(None),  # type: ignore[attr-defined]
                )
                .group_by(field)
                .order_by(field)
            )
            return {value: count for value, count in rows if value}

    @staticmethod
    def _to_company(model: CompanyModel) -> Company:
        return Company(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            website=model.website,
            industry=model.industry,
            country=model.country,
            city=model.city,
            company_size=model.company_size,
            status=model.status,
            source=model.source,
            notes=model.notes,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _ensure_development_default(self, session: Session) -> None:
        """Support metadata-only unit databases; Alembic seeds real databases."""
        if session.get(OrganizationModel, self.organization_id) is None:
            session.add(
                OrganizationModel(
                    id=self.organization_id,
                    slug="rapidnest"
                    if self.organization_id == 1
                    else f"org-{self.organization_id}",
                    legal_name="RapidNest Software Solutions",
                    display_name="RapidNest Software Solutions",
                    status="active",
                    default_currency="INR",
                    timezone="Asia/Kolkata",
                )
            )
            session.flush()
