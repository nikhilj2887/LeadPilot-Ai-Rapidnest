from __future__ import annotations

"""Tenant-aware proposal workspace rendered through the protected application."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import streamlit as st
from pydantic import ValidationError

from leadpilot.application.ai_foundation import AIConfigurationError, AIError
from leadpilot.application.auth import AuthorizationError
from leadpilot.application.offering_recommendations import RecommendationError
from leadpilot.application.proposals import (
    TRANSITIONS,
    ProposalFilters,
    ProposalInput,
    ProposalItemInput,
    ProposalItemType,
    ProposalSectionInput,
    ProposalStatus,
    ProposalValidationError,
)
from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.components import page_header


def render(container: Container) -> None:
    page_header(
        "Proposal Workspace",
        "Build, price, review, and track client proposals for this organization.",
        eyebrow="Proposal engine",
    )
    flash = st.session_state.pop("proposal_flash", None)
    if flash:
        st.success(flash)
    service = container.proposals
    metrics = service.metrics()
    for column, (label, value) in zip(
        st.columns(5),
        (
            ("Total", metrics.total),
            ("Drafts", metrics.drafts),
            ("In review", metrics.in_review),
            ("Accepted", metrics.accepted),
            ("Pipeline value", f"{metrics.pipeline_value:,.2f}"),
        ),
        strict=True,
    ):
        column.metric(label, value)

    workspace, create = st.tabs(("Dashboard", "Create proposal"))
    with workspace:
        _dashboard(container)
    with create:
        _create(container)


def _dashboard(container: Container) -> None:
    service = container.proposals
    controls = st.columns((3, 1, 1))
    query = controls[0].text_input(
        "Search proposals", placeholder="Proposal number or title"
    )
    status_label = controls[1].selectbox(
        "Status", ("All", *(status.value for status in ProposalStatus))
    )
    page_number = int(controls[2].number_input("Page", min_value=1, value=1, step=1))
    page = service.list_proposals(
        ProposalFilters(
            query=query,
            status=None if status_label == "All" else ProposalStatus(status_label),
        ),
        page=page_number,
        page_size=20,
    )
    st.caption(f"Showing {len(page.items)} of {page.total} proposals")
    if not page.items:
        st.info("No proposals match the current filters.")
        return
    st.dataframe(
        [
            {
                "Number": proposal.proposal_number,
                "Title": proposal.title,
                "Company": proposal.company_name,
                "Status": proposal.status.value.replace("_", " ").title(),
                "Total": f"{proposal.currency} {proposal.total_amount:,.2f}",
                "Updated": proposal.updated_at,
            }
            for proposal in page.items
        ],
        hide_index=True,
        width="stretch",
    )
    labels = {
        proposal.id: f"{proposal.proposal_number} · {proposal.title}"
        for proposal in page.items
    }
    proposal_id = st.selectbox("Open proposal", labels, format_func=labels.__getitem__)
    _detail(container, proposal_id)


def _create(container: Container) -> None:
    companies = container.companies.list_companies()
    if not companies:
        st.info("Create a company before starting a proposal.")
        return
    company_labels = {company.id: company.name for company in companies}
    with st.form("proposal_create"):
        st.subheader("Proposal details")
        company_id = st.selectbox(
            "Company", company_labels, format_func=company_labels.__getitem__
        )
        title = st.text_input("Title", max_chars=300)
        columns = st.columns(2)
        currency = columns[0].text_input("Currency", value="INR", max_chars=3)
        valid_until = columns[1].date_input(
            "Valid until", value=datetime.now(UTC).date() + timedelta(days=30)
        )
        summary = st.text_area("Executive summary")
        requirements = st.text_area("Client requirements")
        notes = st.text_area("Internal notes")
        submitted = st.form_submit_button("Create draft", type="primary")
    if submitted:
        _mutate(
            lambda: container.proposals.create_proposal(
                ProposalInput(
                    company_id=company_id,
                    title=title,
                    currency=currency,
                    valid_until=valid_until,
                    summary=summary or None,
                    client_requirements=requirements or None,
                    internal_notes=notes or None,
                )
            ),
            "Draft proposal created with the standard section structure.",
        )


def _detail(container: Container, proposal_id: int) -> None:
    service = container.proposals
    proposal = service.get_proposal(proposal_id)
    st.divider()
    st.subheader(proposal.title)
    st.caption(
        f"{proposal.proposal_number} · {proposal.company_name} · "
        f"{proposal.status.value.replace('_', ' ').title()}"
    )
    summary, items, recommendations, sections, history = st.tabs(
        (
            "Summary",
            "Offerings & pricing",
            "AI Recommendations",
            "Sections",
            "Versions & activity",
        )
    )
    with summary:
        st.write(proposal.summary or "No executive summary yet.")
        columns = st.columns(4)
        columns[0].metric("Subtotal", f"{proposal.subtotal:,.2f}")
        columns[1].metric("Discount", f"{proposal.discount_amount:,.2f}")
        columns[2].metric("Tax", f"{proposal.tax_amount:,.2f}")
        columns[3].metric("Total", f"{proposal.total_amount:,.2f}")
        with st.expander("Edit proposal details"):
            with st.form(f"proposal_edit_{proposal_id}"):
                title = st.text_input("Title", value=proposal.title)
                summary_text = st.text_area(
                    "Executive summary", value=proposal.summary or ""
                )
                requirements = st.text_area(
                    "Client requirements",
                    value=proposal.client_requirements or "",
                )
                notes = st.text_area(
                    "Internal notes", value=proposal.internal_notes or ""
                )
                save_details = st.form_submit_button("Save details")
            if save_details:
                _mutate(
                    lambda: service.update_proposal(
                        proposal_id,
                        ProposalInput(
                            company_id=proposal.company_id,
                            discovery_scan_id=proposal.discovery_scan_id,
                            title=title,
                            currency=proposal.currency,
                            valid_until=proposal.valid_until,
                            summary=summary_text or None,
                            client_requirements=requirements or None,
                            recommended_approach=proposal.recommended_approach,
                            implementation_plan=proposal.implementation_plan,
                            commercial_notes=proposal.commercial_notes,
                            terms_and_conditions=proposal.terms_and_conditions,
                            internal_notes=notes or None,
                        ),
                    ),
                    "Proposal details saved.",
                )
        available = tuple(TRANSITIONS[proposal.status])
        if available:
            target = st.selectbox(
                "Move to status",
                available,
                format_func=lambda value: value.value.replace("_", " ").title(),
            )
            if st.button("Update status", type="primary"):
                _mutate(
                    lambda: service.transition_status(proposal_id, target),
                    f"Proposal moved to {target.value.replace('_', ' ').title()}.",
                )
        delete_confirm = st.checkbox(
            "I understand permanent deletion cannot be undone",
            key=f"delete_confirm_{proposal_id}",
        )
        if st.button(
            "Delete proposal",
            disabled=not delete_confirm or proposal.status == ProposalStatus.ACCEPTED,
        ):
            _mutate(lambda: service.delete_proposal(proposal_id), "Proposal deleted.")

    with items:
        proposal_items = service.list_items(proposal_id)
        if proposal_items:
            st.dataframe(
                [
                    {
                        "Offering": item.title,
                        "Qty": item.quantity,
                        "Unit price": item.unit_price,
                        "Discount": item.discount_amount,
                        "Tax %": item.tax_rate,
                        "Total": item.line_total,
                        "Optional": item.is_optional,
                    }
                    for item in proposal_items
                ],
                hide_index=True,
                width="stretch",
            )
            item_labels = {
                item.id: f"{item.title} · {proposal.currency} {item.line_total:,.2f}"
                for item in proposal_items
            }
            selected_item_id = st.selectbox(
                "Select offering", item_labels, format_func=item_labels.__getitem__
            )
            if st.button("Remove selected offering"):
                _mutate(
                    lambda: service.delete_item(proposal_id, selected_item_id),
                    "Offering removed.",
                )
        catalog_page = container.service_catalog.list_active_products()
        if catalog_page.items:
            with st.expander("Add from Service Catalog"):
                product_labels = {
                    product.id: (
                        f"{product.name} · {product.currency} "
                        f"{product.base_price or Decimal(0):,.2f}"
                    )
                    for product in catalog_page.items
                }
                product_id = st.selectbox(
                    "Catalog offering",
                    product_labels,
                    format_func=product_labels.__getitem__,
                )
                catalog_columns = st.columns(3)
                catalog_quantity = catalog_columns[0].number_input(
                    "Catalog quantity", min_value=0.01, value=1.0
                )
                catalog_tax = catalog_columns[1].number_input(
                    "Catalog tax %",
                    min_value=0.0,
                    max_value=100.0,
                    value=0.0,
                )
                catalog_optional = catalog_columns[2].checkbox(
                    "Catalog item is optional"
                )
                if st.button("Add catalog offering"):
                    _mutate(
                        lambda: service.add_catalog_item(
                            proposal_id,
                            product_id,
                            quantity=Decimal(str(catalog_quantity)),
                            tax_rate=Decimal(str(catalog_tax)),
                            is_optional=catalog_optional,
                        ),
                        "Catalog offering added.",
                    )
        with st.expander("Add manual offering"):
            with st.form(f"item_add_{proposal_id}"):
                title = st.text_input("Offering title")
                description = st.text_area("Description")
                columns = st.columns(4)
                quantity = columns[0].number_input(
                    "Quantity", min_value=0.01, value=1.0
                )
                price = columns[1].number_input("Unit price", min_value=0.0, value=0.0)
                discount = columns[2].number_input("Discount", min_value=0.0, value=0.0)
                tax = columns[3].number_input(
                    "Tax %", min_value=0.0, max_value=100.0, value=0.0
                )
                optional = st.checkbox("Optional item")
                add = st.form_submit_button("Add offering")
            if add:
                _mutate(
                    lambda: service.add_manual_item(
                        proposal_id,
                        ProposalItemInput(
                            item_type=ProposalItemType.CUSTOM,
                            title=title,
                            description=description or None,
                            quantity=Decimal(str(quantity)),
                            unit_price=Decimal(str(price)),
                            discount_amount=Decimal(str(discount)),
                            tax_rate=Decimal(str(tax)),
                            is_optional=optional,
                            display_order=len(proposal_items),
                        ),
                    ),
                    "Offering added.",
                )

    with sections:
        for section in service.list_sections(proposal_id):
            with st.expander(section.title):
                with st.form(f"section_{section.id}"):
                    title = st.text_input("Title", value=section.title)
                    content = st.text_area("Content", value=section.content, height=180)
                    enabled = st.checkbox(
                        "Include in proposal", value=section.is_enabled
                    )
                    save = st.form_submit_button("Save section")
                if save:
                    _mutate(
                        lambda s=section, t=title, c=content, e=enabled: (
                            service.update_section(
                                proposal_id,
                                s.id,
                                ProposalSectionInput(
                                    title=t,
                                    content=c,
                                    is_enabled=e,
                                    display_order=s.display_order,
                                ),
                            )
                        ),
                        "Section saved.",
                    )

    with recommendations:
        _recommendations(container, proposal_id, proposal.company_id)

    with history:
        change_summary = st.text_input(
            "Version note", max_chars=500, key=f"version_note_{proposal_id}"
        )
        if st.button("Create immutable version snapshot"):
            _mutate(
                lambda: service.create_version(proposal_id, change_summary or None),
                "Version snapshot created.",
            )
        st.button("PDF Export", disabled=True)
        st.button("Email proposal", disabled=True)
        for version in service.list_versions(proposal_id):
            st.write(
                f"Version {version.version_number} · "
                f"{version.change_summary or 'No change note'}"
            )
        for activity in service.list_activities(proposal_id):
            st.caption(
                f"{activity.created_at} · "
                f"{activity.activity_type.replace('_', ' ').title()}"
            )


def _mutate(operation: object, message: str) -> None:
    try:
        operation()  # type: ignore[operator]
    except (
        AuthorizationError,
        AIError,
        RecommendationError,
        ProposalValidationError,
        ValidationError,
    ) as exc:
        st.error(str(exc))
        return
    st.session_state.proposal_flash = message
    st.rerun()


def _recommendations(container: Container, proposal_id: int, company_id: int) -> None:
    service = container.offering_recommendations
    st.subheader("Opportunity Context")
    company = container.companies.get_company(company_id)
    scan = container.discovery.latest_for_company(company_id)
    st.caption(
        f"{company.name} · {company.industry or 'Industry unconfirmed'} · "
        f"{company.website or 'No website'} · "
        f"Discovery: {scan.status if scan else 'Unavailable'}"
    )
    try:
        config = container.ai_orchestration.resolve_provider_configuration()
    except AIConfigurationError:
        config = None
        st.warning("AI is not configured. Existing recommendations remain available.")
    controls = st.columns(4)
    candidate_limit = int(controls[0].number_input("Candidate limit", 1, 30, 15))
    threshold = int(controls[1].number_input("Minimum score", 0, 100, 20))
    if controls[2].button("Generate Recommendations", disabled=config is None):
        _mutate(
            lambda: service.generate_recommendations(
                proposal_id,
                company_id,
                candidate_limit=candidate_limit,
                minimum_candidate_score=threshold,
            ),
            "Recommendations generated for human review.",
        )
    if controls[3].button("Regenerate Recommendations", disabled=config is None):
        _mutate(
            lambda: service.generate_recommendations(
                proposal_id,
                company_id,
                candidate_limit=candidate_limit,
                minimum_candidate_score=threshold,
                force_regenerate=True,
            ),
            "Prior pending recommendations superseded.",
        )
    records = service.list_recommendations(proposal_id)
    st.subheader("Recommended Offerings")
    if not records:
        st.info("No recommendation history exists for this proposal.")
    for record in records:
        confidence = (
            "High"
            if record.match_score >= 80
            else "Medium"
            if record.match_score >= 60
            else "Low"
        )
        with st.expander(
            f"Catalog #{record.service_catalog_id} · {record.match_score}% "
            f"{confidence} · {record.status.value.replace('_', ' ').title()}"
        ):
            st.write(record.recommendation_reason)
            st.caption(
                f"Priority {record.priority.value} · Deterministic score "
                f"{record.deterministic_score} · {record.suggested_scope}"
            )
            actions = st.columns(3)
            if actions[0].button(
                "Approve",
                key=f"approve_rec_{record.id}",
                disabled=record.status.value != "PENDING_REVIEW",
            ):
                _mutate(
                    lambda r=record: service.approve_recommendation(r.id),
                    "Recommendation approved.",
                )
            if actions[1].button(
                "Reject",
                key=f"reject_rec_{record.id}",
                disabled=record.status.value != "PENDING_REVIEW",
            ):
                _mutate(
                    lambda r=record: service.reject_recommendation(r.id),
                    "Recommendation rejected.",
                )
            if actions[2].button(
                "Add to Proposal",
                key=f"add_rec_{record.id}",
                disabled=record.status.value != "APPROVED",
            ):
                _mutate(
                    lambda r=record: service.add_recommendation_to_proposal(r.id),
                    "Approved offering added with catalog pricing.",
                )
    st.subheader("Unmatched Opportunities")
    st.caption(
        "Unmatched opportunities are informational and never create catalog items."
    )
    st.subheader("Recommendation History")
    st.caption(f"{len(records)} persisted recommendation records.")
