from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.auth import AuthorizationError
from leadpilot.application.organizations import OrganizationCreate
from leadpilot.application.service_catalog import (
    PricingModel,
    ProductFilters,
    ProductInput,
    ProductNotFoundError,
    ProductSort,
    ProductValidationError,
    ServiceCatalogService,
)
from leadpilot.infrastructure.database.base import Base
from leadpilot.infrastructure.database.organization_repository import (
    OrganizationRepository,
)
from leadpilot.infrastructure.database.service_catalog_repository import (
    ServiceCatalogRepository,
)


def product_values(
    name: str,
    *,
    category: str = "Automation",
    industry: str = "Healthcare",
    pricing_model: PricingModel = PricingModel.FIXED,
    base_price: Decimal | None = Decimal("5000.00"),
    display_order: int = 0,
    active: bool = True,
) -> ProductInput:
    return ProductInput(
        name=name,
        category=category,
        short_description=f"{name} short description",
        detailed_description=f"Detailed description for {name}",
        problems_solved=("Manual work",),
        business_benefits=("Faster delivery",),
        deliverables=("Implementation",),
        target_industries=(industry,),
        pricing_model=pricing_model,
        base_price=base_price,
        currency="usd",
        estimated_timeline="6 weeks",
        tags=("AI", "Automation"),
        display_order=display_order,
        is_active=active,
    )


@pytest.fixture
def catalogs():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    organizations = OrganizationRepository(factory)
    first = organizations.create(
        OrganizationCreate(
            slug="catalog-a",
            display_name="Catalog A",
            default_currency="USD",
            timezone="UTC",
        )
    )
    second = organizations.create(
        OrganizationCreate(
            slug="catalog-b",
            display_name="Catalog B",
            default_currency="USD",
            timezone="UTC",
        )
    )
    return (
        ServiceCatalogRepository(factory, first.id),
        ServiceCatalogRepository(factory, second.id),
    )


def test_product_validation_normalizes_and_rejects_invalid_values() -> None:
    values = product_values("  AI Automation  ")
    assert values.name == "AI Automation"
    assert values.currency == "USD"
    assert values.tags == ("AI", "Automation")
    with pytest.raises(ValidationError):
        product_values("")
    with pytest.raises(ValidationError, match="Base price"):
        product_values("Hourly", pricing_model=PricingModel.HOURLY, base_price=None)
    with pytest.raises(ValidationError):
        product_values("Negative", base_price=Decimal(-1))
    with pytest.raises(ValidationError):
        ProductInput(
            name="Valid",
            category="Automation",
            short_description="Description",
            currency="US1",
        )
    with pytest.raises(ValidationError):
        product_values("x" * 201)


def test_crud_archive_restore_delete_and_audit(catalogs) -> None:
    repository, _ = catalogs
    audits: list[tuple[str, str, str]] = []
    service = ServiceCatalogService(repository, audit=lambda *item: audits.append(item))
    created = service.create_product(product_values("Workflow Automation"))
    assert service.get_product(created.id).name == "Workflow Automation"
    assert service.get_product_by_id(created.id).currency == "USD"

    updated = service.update_product(
        created.id,
        product_values("Workflow Platform", category="Software"),
    )
    assert updated.category == "Software"
    assert not service.archive_product(created.id).is_active
    assert service.restore_product(created.id).is_active
    service.delete_product(created.id)
    with pytest.raises(ProductNotFoundError):
        service.get_product(created.id)
    assert [item[0] for item in audits] == [
        "CREATE_PRODUCT",
        "UPDATE_PRODUCT",
        "ARCHIVE_PRODUCT",
        "RESTORE_PRODUCT",
        "DELETE_PRODUCT",
    ]


def test_duplicate_names_are_scoped_and_case_insensitive(catalogs) -> None:
    first, second = catalogs
    first_service = ServiceCatalogService(first)
    second_service = ServiceCatalogService(second)
    first_service.create_product(product_values("AI Assistant"))
    with pytest.raises(ProductValidationError, match="already exists"):
        first_service.create_product(product_values("ai assistant"))
    assert second_service.create_product(product_values("AI Assistant")).id is not None


def test_repository_enforces_tenant_isolation_for_every_mutation(catalogs) -> None:
    first, second = catalogs
    product = first.create(product_values("Private Service"))
    assert second.get_by_id(product.id) is None
    assert second.update(product.id, product_values("Compromised")) is None
    assert not second.delete(product.id)
    assert (
        second.list(
            ProductFilters(query="Private"),
            page=1,
            page_size=25,
            sort=ProductSort.NAME,
            descending=False,
        ).total
        == 0
    )
    assert first.get_by_id(product.id) is not None


def test_search_filter_and_catalog_shortcuts(catalogs) -> None:
    repository, _ = catalogs
    service = ServiceCatalogService(repository)
    service.create_product(
        product_values(
            "Healthcare Bot",
            category="AI",
            industry="Healthcare",
            pricing_model=PricingModel.MONTHLY,
            base_price=Decimal("800.00"),
        )
    )
    service.create_product(
        product_values(
            "Retail Portal",
            category="Web",
            industry="Retail",
            active=False,
        )
    )
    assert service.search_products("bot").total == 1
    assert service.list_active_products().total == 1
    assert service.list_by_category("Web").items[0].name == "Retail Portal"
    assert service.list_by_industry("Healthcare").items[0].name == "Healthcare Bot"
    filtered = service.filter_products(
        ProductFilters(
            category="AI",
            industry="Healthcare",
            pricing_model=PricingModel.MONTHLY,
            is_active=True,
        )
    )
    assert [item.name for item in filtered.items] == ["Healthcare Bot"]
    assert service.categories() == ["AI", "Web"]
    assert service.industries() == ["Healthcare", "Retail"]
    assert service.metrics().total == 2
    assert service.metrics().active == 1


def test_pagination_sorting_and_invalid_page_controls(catalogs) -> None:
    repository, _ = catalogs
    service = ServiceCatalogService(repository)
    for order, name in enumerate(("Zulu", "Alpha", "Mike"), 1):
        service.create_product(product_values(name, display_order=order))
    first_page = service.filter_products(page=1, page_size=2, sort=ProductSort.NAME)
    second_page = service.filter_products(page=2, page_size=2, sort=ProductSort.NAME)
    descending = service.filter_products(
        page=1,
        page_size=3,
        sort=ProductSort.NAME,
        descending=True,
    )
    assert first_page.total == 3
    assert [item.name for item in first_page.items] == ["Alpha", "Mike"]
    assert [item.name for item in second_page.items] == ["Zulu"]
    assert [item.name for item in descending.items] == ["Zulu", "Mike", "Alpha"]
    with pytest.raises(ProductValidationError, match="Page"):
        service.filter_products(page=0)
    with pytest.raises(ProductValidationError, match="Page size"):
        service.filter_products(page_size=101)


def test_write_permission_is_checked_before_repository_mutation(catalogs) -> None:
    repository, _ = catalogs

    def deny() -> None:
        raise AuthorizationError("Manager access is required.")

    service = ServiceCatalogService(repository, authorize_write=deny)
    with pytest.raises(AuthorizationError, match="Manager"):
        service.create_product(product_values("Blocked"))
    assert repository.metrics().total == 0


def test_service_catalog_migration_backfills_and_indexes(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'catalog-migration.db'}"
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "20260729_0006")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE organization_services SET full_description = "
            "'Legacy description' WHERE id = 1"
        )
    command.upgrade(config, "head")

    inspector = inspect(engine)
    columns = {
        column["name"] for column in inspector.get_columns("organization_services")
    }
    assert {
        "detailed_description",
        "problems_solved",
        "business_benefits",
        "deliverables",
        "target_industries",
        "pricing_model",
        "base_price",
        "currency",
        "estimated_timeline",
        "tags",
    } <= columns
    indexes = {
        index["name"] for index in inspector.get_indexes("organization_services")
    }
    assert {
        "ix_org_services_org_category",
        "ix_org_services_org_pricing_model",
        "ix_org_services_org_active",
    } <= indexes
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT detailed_description FROM organization_services WHERE id = 1"
            ).scalar_one()
            == "Legacy description"
        )
