from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadpilot.application.service_catalog import (
    CatalogMetrics,
    PricingModel,
    Product,
    ProductFilters,
    ProductInput,
    ProductPage,
    ProductSort,
    ProductValidationError,
)
from leadpilot.infrastructure.database.models import OrganizationServiceModel


class ServiceCatalogRepository:
    """Tenant-bound SQLAlchemy persistence for products and services."""

    def __init__(
        self, session_factory: Callable[[], Session], organization_id: int
    ) -> None:
        self._session_factory = session_factory
        self.organization_id = organization_id

    def create(self, values: ProductInput) -> Product:
        with self._session_factory() as session, session.begin():
            if self._name_exists(session, values.name):
                raise ProductValidationError(
                    "A product with this name already exists in this organization"
                )
            model = OrganizationServiceModel(
                organization_id=self.organization_id,
                **self._values(values),
            )
            session.add(model)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ProductValidationError(
                    "A product with this name already exists in this organization"
                ) from exc
            session.refresh(model)
            return self._product(model)

    def update(self, product_id: int, values: ProductInput) -> Product | None:
        with self._session_factory() as session, session.begin():
            model = self._tenant_product(session, product_id)
            if model is None:
                return None
            if self._name_exists(session, values.name, excluding_id=product_id):
                raise ProductValidationError(
                    "A product with this name already exists in this organization"
                )
            for field, value in self._values(values).items():
                setattr(model, field, value)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ProductValidationError(
                    "A product with this name already exists in this organization"
                ) from exc
            session.refresh(model)
            return self._product(model)

    def delete(self, product_id: int) -> bool:
        with self._session_factory() as session, session.begin():
            model = self._tenant_product(session, product_id)
            if model is None:
                return False
            session.delete(model)
            return True

    def get_by_id(self, product_id: int) -> Product | None:
        with self._session_factory() as session:
            model = self._tenant_product(session, product_id)
            return self._product(model) if model else None

    def get_by_name(self, name: str) -> Product | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(OrganizationServiceModel).where(
                    OrganizationServiceModel.organization_id == self.organization_id,
                    func.lower(OrganizationServiceModel.name)
                    == name.strip().casefold(),
                )
            )
            return self._product(model) if model else None

    def list(
        self,
        filters: ProductFilters,
        *,
        page: int,
        page_size: int,
        sort: ProductSort,
        descending: bool,
    ) -> ProductPage:
        predicates = self._predicates(filters)
        sort_columns = {
            ProductSort.DISPLAY_ORDER: (
                OrganizationServiceModel.display_order,
                OrganizationServiceModel.name,
            ),
            ProductSort.NAME: (OrganizationServiceModel.name,),
            ProductSort.CATEGORY: (
                OrganizationServiceModel.category,
                OrganizationServiceModel.name,
            ),
            ProductSort.PRICE: (
                OrganizationServiceModel.base_price,
                OrganizationServiceModel.name,
            ),
            ProductSort.UPDATED: (
                OrganizationServiceModel.updated_at,
                OrganizationServiceModel.id,
            ),
        }[sort]
        direction = desc if descending else asc
        statement = (
            select(OrganizationServiceModel)
            .where(*predicates)
            .order_by(*(direction(column) for column in sort_columns))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        count_statement = (
            select(func.count(OrganizationServiceModel.id))
            .select_from(OrganizationServiceModel)
            .where(*predicates)
        )
        with self._session_factory() as session:
            total = session.scalar(count_statement) or 0
            items = tuple(self._product(model) for model in session.scalars(statement))
        return ProductPage(items, total, page, page_size)

    def list_categories(self) -> list[str]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(OrganizationServiceModel.category)
                    .where(
                        OrganizationServiceModel.organization_id
                        == self.organization_id,
                        OrganizationServiceModel.category.is_not(None),
                    )
                    .distinct()
                    .order_by(OrganizationServiceModel.category)
                )
            )

    def list_industries(self) -> list[str]:
        with self._session_factory() as session:
            values = session.scalars(
                select(OrganizationServiceModel.target_industries).where(
                    OrganizationServiceModel.organization_id == self.organization_id
                )
            )
            return sorted(
                {
                    industry
                    for value in values
                    for industry in self._decode(value)
                    if industry
                },
                key=str.casefold,
            )

    def metrics(self) -> CatalogMetrics:
        with self._session_factory() as session:
            total = (
                session.scalar(
                    select(func.count(OrganizationServiceModel.id)).where(
                        OrganizationServiceModel.organization_id == self.organization_id
                    )
                )
                or 0
            )
            active = (
                session.scalar(
                    select(func.count(OrganizationServiceModel.id)).where(
                        OrganizationServiceModel.organization_id
                        == self.organization_id,
                        OrganizationServiceModel.is_active.is_(True),
                    )
                )
                or 0
            )
            categories = (
                session.scalar(
                    select(
                        func.count(func.distinct(OrganizationServiceModel.category))
                    ).where(
                        OrganizationServiceModel.organization_id
                        == self.organization_id,
                        OrganizationServiceModel.category.is_not(None),
                    )
                )
                or 0
            )
            pricing_models = (
                session.scalar(
                    select(
                        func.count(
                            func.distinct(OrganizationServiceModel.pricing_model)
                        )
                    ).where(
                        OrganizationServiceModel.organization_id == self.organization_id
                    )
                )
                or 0
            )
        return CatalogMetrics(total, active, categories, pricing_models)

    def _predicates(self, filters: ProductFilters) -> list[Any]:
        predicates: list[Any] = [
            OrganizationServiceModel.organization_id == self.organization_id
        ]
        if filters.query.strip():
            pattern = f"%{filters.query.strip().casefold()}%"
            predicates.append(
                or_(
                    func.lower(OrganizationServiceModel.name).like(pattern),
                    func.lower(OrganizationServiceModel.category).like(pattern),
                    func.lower(OrganizationServiceModel.short_description).like(
                        pattern
                    ),
                    func.lower(OrganizationServiceModel.detailed_description).like(
                        pattern
                    ),
                    func.lower(OrganizationServiceModel.tags).like(pattern),
                )
            )
        if filters.category:
            predicates.append(
                func.lower(OrganizationServiceModel.category)
                == filters.category.casefold()
            )
        if filters.industry:
            predicates.append(
                func.lower(OrganizationServiceModel.target_industries).like(
                    f"%{filters.industry.casefold()}%"
                )
            )
        if filters.pricing_model:
            predicates.append(
                OrganizationServiceModel.pricing_model == filters.pricing_model.value
            )
        if filters.is_active is not None:
            predicates.append(OrganizationServiceModel.is_active.is_(filters.is_active))
        return predicates

    def _tenant_product(
        self, session: Session, product_id: int
    ) -> OrganizationServiceModel | None:
        return session.scalar(
            select(OrganizationServiceModel).where(
                OrganizationServiceModel.id == product_id,
                OrganizationServiceModel.organization_id == self.organization_id,
            )
        )

    def _name_exists(
        self, session: Session, name: str, *, excluding_id: int | None = None
    ) -> bool:
        statement = select(OrganizationServiceModel.id).where(
            OrganizationServiceModel.organization_id == self.organization_id,
            func.lower(OrganizationServiceModel.name) == name.strip().casefold(),
        )
        if excluding_id is not None:
            statement = statement.where(OrganizationServiceModel.id != excluding_id)
        return session.scalar(statement.limit(1)) is not None

    @classmethod
    def _values(cls, values: ProductInput) -> dict[str, Any]:
        return {
            "name": values.name,
            "category": values.category,
            "short_description": values.short_description,
            "full_description": values.detailed_description,
            "detailed_description": values.detailed_description,
            "problems_solved": json.dumps(values.problems_solved),
            "business_benefits": json.dumps(values.business_benefits),
            "deliverables": json.dumps(values.deliverables),
            "target_industries": json.dumps(values.target_industries),
            "pricing_model": values.pricing_model.value,
            "base_price": values.base_price,
            "currency": values.currency,
            "estimated_timeline": values.estimated_timeline,
            "tags": json.dumps(values.tags),
            "display_order": values.display_order,
            "is_active": values.is_active,
        }

    @classmethod
    def _product(cls, model: OrganizationServiceModel) -> Product:
        return Product(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            category=model.category or "Uncategorized",
            short_description=model.short_description or "",
            detailed_description=(model.detailed_description or model.full_description),
            problems_solved=cls._decode(model.problems_solved),
            business_benefits=cls._decode(model.business_benefits),
            deliverables=cls._decode(model.deliverables),
            target_industries=cls._decode(model.target_industries),
            pricing_model=PricingModel(model.pricing_model),
            base_price=model.base_price,
            currency=model.currency,
            estimated_timeline=model.estimated_timeline,
            tags=cls._decode(model.tags),
            display_order=model.display_order,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _decode(value: str | None) -> tuple[str, ...]:
        try:
            decoded = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            return ()
        return tuple(str(item) for item in decoded if str(item).strip())
