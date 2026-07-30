from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PricingModel(StrEnum):
    FIXED = "FIXED"
    HOURLY = "HOURLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    CUSTOM = "CUSTOM"


class ProductSort(StrEnum):
    DISPLAY_ORDER = "DISPLAY_ORDER"
    NAME = "NAME"
    CATEGORY = "CATEGORY"
    PRICE = "PRICE"
    UPDATED = "UPDATED"


class ProductValidationError(ValueError):
    """Raised when catalog input violates business validation."""


class ProductNotFoundError(LookupError):
    """Raised when a product does not exist in the selected organization."""


class ProductInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=120)
    short_description: str = Field(min_length=1, max_length=500)
    detailed_description: str | None = None
    problems_solved: tuple[str, ...] = ()
    business_benefits: tuple[str, ...] = ()
    deliverables: tuple[str, ...] = ()
    target_industries: tuple[str, ...] = ()
    pricing_model: PricingModel = PricingModel.CUSTOM
    base_price: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    currency: str = Field(default="INR", min_length=3, max_length=3)
    estimated_timeline: str | None = Field(default=None, max_length=200)
    tags: tuple[str, ...] = ()
    display_order: int = Field(default=0, ge=0)
    is_active: bool = True

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if not value.isalpha():
            raise ValueError("Currency must be a three-letter code")
        return value.upper()

    @field_validator(
        "problems_solved",
        "business_benefits",
        "deliverables",
        "target_industries",
        "tags",
    )
    @classmethod
    def normalize_lists(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(value.strip() for value in values if value.strip())
        )
        if any(len(value) > 200 for value in normalized):
            raise ValueError("List entries must be 200 characters or fewer")
        return normalized

    @model_validator(mode="after")
    def validate_price(self) -> ProductInput:
        if self.pricing_model != PricingModel.CUSTOM and self.base_price is None:
            raise ValueError("Base price is required for this pricing model")
        return self


@dataclass(frozen=True, slots=True)
class Product:
    id: int
    organization_id: int
    name: str
    category: str
    short_description: str
    detailed_description: str | None
    problems_solved: tuple[str, ...]
    business_benefits: tuple[str, ...]
    deliverables: tuple[str, ...]
    target_industries: tuple[str, ...]
    pricing_model: PricingModel
    base_price: Decimal | None
    currency: str
    estimated_timeline: str | None
    tags: tuple[str, ...]
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProductFilters:
    query: str = ""
    category: str | None = None
    industry: str | None = None
    pricing_model: PricingModel | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class ProductPage:
    items: tuple[Product, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class CatalogMetrics:
    total: int
    active: int
    categories: int
    pricing_models: int


class ProductRepository(Protocol):
    def create(self, values: ProductInput) -> Product: ...
    def update(self, product_id: int, values: ProductInput) -> Product | None: ...
    def delete(self, product_id: int) -> bool: ...
    def get_by_id(self, product_id: int) -> Product | None: ...
    def get_by_name(self, name: str) -> Product | None: ...
    def list(
        self,
        filters: ProductFilters,
        *,
        page: int,
        page_size: int,
        sort: ProductSort,
        descending: bool,
    ) -> ProductPage: ...
    def list_categories(self) -> list[str]: ...
    def list_industries(self) -> list[str]: ...
    def metrics(self) -> CatalogMetrics: ...


class ServiceCatalogService:
    """Application operations for one organization-owned product catalog."""

    def __init__(
        self,
        repository: ProductRepository,
        *,
        authorize_write: Callable[[], None] | None = None,
        audit: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._repository = repository
        self._authorize_write = authorize_write
        self._audit = audit

    def create_product(self, values: ProductInput) -> Product:
        self._authorize()
        self._ensure_unique(values.name)
        product = self._repository.create(values)
        self._log("CREATE_PRODUCT", product.id)
        return product

    def update_product(self, product_id: int, values: ProductInput) -> Product:
        self._authorize()
        existing_name = self._repository.get_by_name(values.name)
        if existing_name and existing_name.id != product_id:
            raise ProductValidationError(
                "A product with this name already exists in this organization"
            )
        product = self._repository.update(product_id, values)
        if product is None:
            raise ProductNotFoundError(f"Product {product_id} was not found")
        self._log("UPDATE_PRODUCT", product.id)
        return product

    def delete_product(self, product_id: int) -> None:
        self._authorize()
        if not self._repository.delete(product_id):
            raise ProductNotFoundError(f"Product {product_id} was not found")
        self._log("DELETE_PRODUCT", product_id)

    def archive_product(self, product_id: int) -> Product:
        return self._set_active(product_id, False, "ARCHIVE_PRODUCT")

    def restore_product(self, product_id: int) -> Product:
        return self._set_active(product_id, True, "RESTORE_PRODUCT")

    def get_product(self, product_id: int) -> Product:
        product = self._repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(f"Product {product_id} was not found")
        return product

    def get_product_by_id(self, product_id: int) -> Product:
        return self.get_product(product_id)

    def search_products(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 25,
    ) -> ProductPage:
        return self.filter_products(
            ProductFilters(query=query), page=page, page_size=page_size
        )

    def filter_products(
        self,
        filters: ProductFilters | None = None,
        *,
        page: int = 1,
        page_size: int = 25,
        sort: ProductSort = ProductSort.DISPLAY_ORDER,
        descending: bool = False,
    ) -> ProductPage:
        if page < 1:
            raise ProductValidationError("Page must be at least 1")
        if not 1 <= page_size <= 100:
            raise ProductValidationError("Page size must be between 1 and 100")
        return self._repository.list(
            filters or ProductFilters(),
            page=page,
            page_size=page_size,
            sort=sort,
            descending=descending,
        )

    def list_active_products(self) -> ProductPage:
        return self.filter_products(ProductFilters(is_active=True), page_size=100)

    def list_by_category(self, category: str) -> ProductPage:
        return self.filter_products(ProductFilters(category=category), page_size=100)

    def list_by_industry(self, industry: str) -> ProductPage:
        return self.filter_products(ProductFilters(industry=industry), page_size=100)

    def categories(self) -> list[str]:
        return self._repository.list_categories()

    def industries(self) -> list[str]:
        return self._repository.list_industries()

    def metrics(self) -> CatalogMetrics:
        return self._repository.metrics()

    def _set_active(self, product_id: int, active: bool, action: str) -> Product:
        self._authorize()
        current = self.get_product(product_id)
        values = ProductInput(
            name=current.name,
            category=current.category,
            short_description=current.short_description,
            detailed_description=current.detailed_description,
            problems_solved=current.problems_solved,
            business_benefits=current.business_benefits,
            deliverables=current.deliverables,
            target_industries=current.target_industries,
            pricing_model=current.pricing_model,
            base_price=current.base_price,
            currency=current.currency,
            estimated_timeline=current.estimated_timeline,
            tags=current.tags,
            display_order=current.display_order,
            is_active=active,
        )
        product = self._repository.update(product_id, values)
        if product is None:
            raise ProductNotFoundError(f"Product {product_id} was not found")
        self._log(action, product_id)
        return product

    def _ensure_unique(self, name: str) -> None:
        if self._repository.get_by_name(name) is not None:
            raise ProductValidationError(
                "A product with this name already exists in this organization"
            )

    def _authorize(self) -> None:
        if self._authorize_write:
            self._authorize_write()

    def _log(self, action: str, product_id: int) -> None:
        if self._audit:
            self._audit(action, "product", str(product_id))
