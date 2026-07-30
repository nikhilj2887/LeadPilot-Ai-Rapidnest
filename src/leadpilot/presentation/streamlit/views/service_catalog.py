from __future__ import annotations

"""Tenant-aware product and service catalog."""

from collections.abc import Callable
from decimal import Decimal

import streamlit as st
from pydantic import ValidationError

from leadpilot.application.auth import AuthorizationError
from leadpilot.application.service_catalog import (
    PricingModel,
    Product,
    ProductFilters,
    ProductInput,
    ProductNotFoundError,
    ProductSort,
    ProductValidationError,
)
from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.components import page_header

PAGE_SIZE = 20


def render(container: Container) -> None:
    catalog = container.service_catalog
    page_header(
        "Service Catalog",
        "Manage proposal-ready products and services for the selected organization.",
        eyebrow="Catalog",
    )
    flash = st.session_state.pop("catalog_flash", None)
    if flash:
        st.success(flash)

    metrics = catalog.metrics()
    for column, (label, value) in zip(
        st.columns(4),
        (
            ("Total Products", metrics.total),
            ("Active Products", metrics.active),
            ("Categories", metrics.categories),
            ("Pricing Models", metrics.pricing_models),
        ),
        strict=True,
    ):
        column.metric(label, value)

    top = st.columns((3, 1))
    query = top[0].text_input(
        "Search products",
        key="catalog_search",
        placeholder="Search name, category, description, or tags",
    )
    if top[1].button("Create product", type="primary", width="stretch"):
        st.session_state.catalog_form = "create"
        st.session_state.pop("catalog_selected_id", None)

    categories = catalog.categories()
    industries = catalog.industries()
    filters = st.columns(4)
    category = filters[0].selectbox("Category", ("All", *categories))
    industry = filters[1].selectbox("Industry", ("All", *industries))
    status = filters[2].selectbox("Status", ("All", "Active", "Archived"))
    pricing = filters[3].selectbox(
        "Pricing model", ("All", *(model.value for model in PricingModel))
    )
    controls = st.columns((2, 1, 1))
    sort = controls[0].selectbox(
        "Sort by",
        tuple(ProductSort),
        format_func=lambda value: value.value.replace("_", " ").title(),
    )
    descending = controls[1].checkbox("Descending")
    page_number = int(controls[2].number_input("Page", min_value=1, value=1, step=1))
    product_page = catalog.filter_products(
        ProductFilters(
            query=query,
            category=None if category == "All" else category,
            industry=None if industry == "All" else industry,
            pricing_model=None if pricing == "All" else PricingModel(pricing),
            is_active={"All": None, "Active": True, "Archived": False}[status],
        ),
        page=page_number,
        page_size=PAGE_SIZE,
        sort=sort,
        descending=descending,
    )
    st.caption(
        f"Showing {len(product_page.items)} of {product_page.total} products "
        f"· Page {product_page.page}"
    )
    if product_page.items:
        st.dataframe(
            [
                {
                    "Name": product.name,
                    "Category": product.category,
                    "Pricing": product.pricing_model.value,
                    "Base price": _price(product),
                    "Timeline": product.estimated_timeline or "—",
                    "Status": "Active" if product.is_active else "Archived",
                    "Order": product.display_order,
                }
                for product in product_page.items
            ],
            width="stretch",
            hide_index=True,
        )
        selected_id = st.selectbox(
            "Select product",
            [product.id for product in product_page.items],
            format_func={
                product.id: product.name for product in product_page.items
            }.__getitem__,
            key="catalog_selected_id",
        )
        selected = catalog.get_product(selected_id)
        actions = st.columns(4)
        if actions[0].button("Edit", width="stretch"):
            st.session_state.catalog_form = "edit"
        if selected.is_active:
            if actions[1].button("Archive", width="stretch"):
                _mutate(
                    lambda: catalog.archive_product(selected.id), "Product archived."
                )
        elif actions[1].button("Restore", width="stretch"):
            _mutate(lambda: catalog.restore_product(selected.id), "Product restored.")
        if actions[2].button("Delete", width="stretch"):
            st.session_state.catalog_delete_id = selected.id
        if actions[3].button("Clear selection", width="stretch"):
            st.session_state.pop("catalog_form", None)
            st.session_state.pop("catalog_delete_id", None)
            st.rerun()
        if st.session_state.get("catalog_delete_id") == selected.id:
            st.warning(f'Delete "{selected.name}" permanently? This cannot be undone.')
            confirm, cancel = st.columns(2)
            if confirm.button("Confirm delete", type="primary", width="stretch"):
                _mutate(lambda: catalog.delete_product(selected.id), "Product deleted.")
            if cancel.button("Cancel", width="stretch"):
                st.session_state.pop("catalog_delete_id", None)
                st.rerun()
    else:
        st.info("No products match the current filters.")

    form_mode = st.session_state.get("catalog_form")
    if form_mode == "create":
        _render_form(container, None)
    elif form_mode == "edit" and product_page.items:
        selected_id = st.session_state.get("catalog_selected_id")
        if selected_id:
            _render_form(container, catalog.get_product(selected_id))


def _render_form(container: Container, product: Product | None) -> None:
    catalog = container.service_catalog
    heading = "Edit product" if product else "Create product"
    with (
        st.expander(heading, expanded=True),
        st.form(f"catalog_product_{product.id if product else 'new'}"),
    ):
        left, right = st.columns(2)
        name = left.text_input("Name", product.name if product else "", max_chars=200)
        category = right.text_input(
            "Category", product.category if product else "", max_chars=120
        )
        short_description = st.text_area(
            "Short description",
            product.short_description if product else "",
            max_chars=500,
        )
        detailed_description = st.text_area(
            "Detailed description",
            (product.detailed_description or "") if product else "",
        )
        problems = left.text_area(
            "Problems solved",
            _lines(product.problems_solved) if product else "",
            help="One item per line",
        )
        benefits = right.text_area(
            "Business benefits",
            _lines(product.business_benefits) if product else "",
            help="One item per line",
        )
        deliverables = left.text_area(
            "Deliverables",
            _lines(product.deliverables) if product else "",
            help="One item per line",
        )
        industries = right.text_area(
            "Target industries",
            _lines(product.target_industries) if product else "",
            help="One item per line",
        )
        pricing_options = tuple(PricingModel)
        pricing_model = left.selectbox(
            "Pricing model",
            pricing_options,
            index=pricing_options.index(
                product.pricing_model if product else PricingModel.CUSTOM
            ),
            format_func=lambda value: value.value.title(),
        )
        base_price = right.number_input(
            "Base price",
            min_value=0.0,
            value=float(product.base_price or 0) if product else 0.0,
            step=100.0,
        )
        currency = left.text_input(
            "Currency", product.currency if product else "INR", max_chars=3
        )
        timeline = right.text_input(
            "Estimated timeline",
            (product.estimated_timeline or "") if product else "",
            max_chars=200,
        )
        tags = left.text_area(
            "Tags",
            _lines(product.tags) if product else "",
            help="One tag per line",
        )
        display_order = right.number_input(
            "Display order",
            min_value=0,
            value=product.display_order if product else 0,
            step=1,
        )
        active = st.checkbox("Active", value=product.is_active if product else True)
        submit, cancel = st.columns(2)
        submitted = submit.form_submit_button(
            "Save product", type="primary", width="stretch"
        )
        cancelled = cancel.form_submit_button("Cancel", width="stretch")
        if cancelled:
            st.session_state.pop("catalog_form", None)
            st.rerun()
        if submitted:
            try:
                values = ProductInput(
                    name=name,
                    category=category,
                    short_description=short_description,
                    detailed_description=detailed_description or None,
                    problems_solved=_split(problems),
                    business_benefits=_split(benefits),
                    deliverables=_split(deliverables),
                    target_industries=_split(industries),
                    pricing_model=pricing_model,
                    base_price=Decimal(str(base_price)) if base_price else None,
                    currency=currency,
                    estimated_timeline=timeline or None,
                    tags=_split(tags),
                    display_order=int(display_order),
                    is_active=active,
                )
                if product:
                    catalog.update_product(product.id, values)
                    message = "Product updated."
                else:
                    catalog.create_product(values)
                    message = "Product created."
                st.session_state.catalog_flash = message
                st.session_state.pop("catalog_form", None)
                st.rerun()
            except (
                ValidationError,
                ProductValidationError,
                ProductNotFoundError,
                AuthorizationError,
            ) as exc:
                st.error(str(exc))


def _mutate(operation: Callable[[], object], message: str) -> None:
    try:
        operation()
        st.session_state.catalog_flash = message
        st.session_state.pop("catalog_delete_id", None)
        st.rerun()
    except (ProductNotFoundError, ProductValidationError, AuthorizationError) as exc:
        st.error(str(exc))


def _split(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


def _lines(values: tuple[str, ...]) -> str:
    return "\n".join(values)


def _price(product: Product) -> str:
    if product.base_price is None:
        return "Custom"
    return f"{product.currency} {product.base_price:,.2f}"
