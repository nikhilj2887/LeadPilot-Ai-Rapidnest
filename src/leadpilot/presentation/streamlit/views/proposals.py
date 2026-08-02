from __future__ import annotations

"""Tenant-aware proposal workspace rendered through the protected application."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import streamlit as st
from pydantic import ValidationError

from leadpilot.application.ai_foundation import AIConfigurationError, AIError
from leadpilot.application.auth import AuthorizationError
from leadpilot.application.offering_recommendations import RecommendationError
from leadpilot.application.proposal_email import (
    EmailError,
    ProposalEmailDeliveryStatus,
)
from leadpilot.application.proposal_generation import (
    SUPPORTED_SECTION_KEYS,
    ProposalGenerationError,
    ProposalGenerationStatus,
    ProposalTone,
)
from leadpilot.application.proposal_pdf import ProposalDocumentStatus, ProposalPdfError
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
    summary, items, recommendations, writer, documents, email, sections, history = (
        st.tabs(
            (
                "Summary",
                "Offerings & pricing",
                "AI Recommendations",
                "AI Proposal Writer",
                "Proposal Documents",
                "Email Delivery",
                "Sections",
                "Versions & activity",
            )
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

    with writer:
        _proposal_writer(container, proposal_id)

    with documents:
        _proposal_documents(container, proposal_id)

    with email:
        _proposal_email(container, proposal_id)

    with history:
        change_summary = st.text_input(
            "Version note", max_chars=500, key=f"version_note_{proposal_id}"
        )
        if st.button("Create immutable version snapshot"):
            _mutate(
                lambda: service.create_version(proposal_id, change_summary or None),
                "Version snapshot created.",
            )
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
        ProposalGenerationError,
        ProposalPdfError,
        EmailError,
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


def _proposal_writer(container: Container, proposal_id: int) -> None:
    service = container.proposal_generation
    proposal = container.proposals.get_proposal(proposal_id)
    sections = {
        section.section_key: section
        for section in container.proposals.list_sections(proposal_id)
        if section.section_key in SUPPORTED_SECTION_KEYS
    }
    st.subheader("Generation Context")
    recommendations = container.offering_recommendations.list_recommendations(
        proposal_id
    )
    approved = sum(
        record.status.value in {"APPROVED", "ADDED_TO_PROPOSAL"}
        for record in recommendations
    )
    manual = sum(section.manually_edited for section in sections.values())
    st.caption(
        f"{proposal.proposal_number} · {proposal.company_name} · "
        f"{proposal.status.value.replace('_', ' ').title()} · "
        f"{approved} approved recommendations · "
        f"{len(container.proposals.list_items(proposal_id))} proposal items · "
        f"{manual} manually edited sections"
    )
    try:
        config = container.ai_orchestration.resolve_provider_configuration()
    except AIConfigurationError:
        config = None
        st.warning("AI is not configured. Generation history remains available.")
    selected = st.multiselect(
        "Select narrative sections",
        tuple(sections),
        default=("EXECUTIVE_SUMMARY",) if "EXECUTIVE_SUMMARY" in sections else (),
        format_func=lambda key: sections[key].title,
    )
    tone = st.selectbox(
        "Tone",
        tuple(ProposalTone),
        format_func=lambda value: value.value.title(),
    )
    instructions = st.text_area(
        "Optional instructions",
        max_chars=1500,
        help="Instructions cannot change prices, legal terms, or catalog offerings.",
    )
    controls = st.columns(3)
    if controls[0].button("Generate Draft", disabled=config is None or not selected):
        _mutate(
            lambda: service.generate_proposal_draft(
                proposal_id,
                section_keys=tuple(selected),
                tone=tone,
                instructions=instructions or None,
            ),
            "Draft generated for preview.",
        )
    if controls[1].button(
        "Regenerate Selected Sections", disabled=config is None or not selected
    ):
        _mutate(
            lambda: service.generate_proposal_draft(
                proposal_id,
                section_keys=tuple(selected),
                tone=tone,
                instructions=instructions or None,
                force_regenerate=True,
            ),
            "Selected sections regenerated.",
        )
    drafts = service.list_generation_drafts(proposal_id)
    st.subheader("Draft Preview")
    for draft in drafts:
        with st.expander(
            f"Draft #{draft.id} · {draft.generation_type.value.replace('_', ' ').title()} "
            f"· {draft.status.value.replace('_', ' ').title()}"
        ):
            apply_keys: list[str] = []
            manual_selected = False
            for generated in draft.generated_sections:
                current = sections[generated.section_key]
                st.markdown(f"#### {generated.title}")
                st.caption(f"Current content · Source: {current.content_source}")
                st.text_area(
                    "Current content",
                    current.content,
                    disabled=True,
                    key=f"current_{draft.id}_{generated.section_key}",
                )
                st.caption("Generated preview")
                st.text_area(
                    "Generated content",
                    generated.content,
                    disabled=True,
                    key=f"generated_{draft.id}_{generated.section_key}",
                )
                if current.manually_edited:
                    st.warning("This section contains manual edits.")
                if st.checkbox(
                    "Apply this section",
                    key=f"apply_{draft.id}_{generated.section_key}",
                ):
                    apply_keys.append(generated.section_key)
                    manual_selected |= current.manually_edited
            confirm = st.checkbox(
                "Confirm overwrite of selected manual edits",
                key=f"confirm_manual_{draft.id}",
                disabled=not manual_selected,
            )
            actions = st.columns(2)
            if actions[0].button(
                "Apply Selected Sections",
                key=f"apply_draft_{draft.id}",
                disabled=(
                    draft.status != ProposalGenerationStatus.READY_FOR_REVIEW
                    or not apply_keys
                ),
            ):
                _mutate(
                    lambda d=draft, keys=tuple(apply_keys), confirmed=confirm: (
                        service.apply_selected_sections(
                            d.id,
                            keys,
                            confirm_manual_overwrite=confirmed,
                        )
                    ),
                    "Selected narrative sections applied after versioning.",
                )
            if actions[1].button(
                "Reject Draft",
                key=f"reject_draft_{draft.id}",
                disabled=draft.status != ProposalGenerationStatus.READY_FOR_REVIEW,
            ):
                _mutate(
                    lambda d=draft: service.reject_generation_draft(d.id),
                    "Draft rejected without changing the proposal.",
                )
    st.subheader("Generation History")
    st.caption(f"{len(drafts)} generation drafts retained.")


def _proposal_documents(container: Container, proposal_id: int) -> None:
    st.caption("PDF Export")
    proposal = container.proposals.get_proposal(proposal_id)
    sections = tuple(
        section
        for section in container.proposals.list_sections(proposal_id)
        if section.is_enabled and section.content.strip()
    )
    items = container.proposals.list_items(proposal_id)
    organization = container.organization_context.organization
    branding = container.organizations.get_branding(organization.id)
    st.subheader("PDF Readiness")
    st.caption(
        f"{proposal.proposal_number} · {proposal.company_name} · "
        f"{len(sections)} narrative sections · {len(items)} items · "
        f"{proposal.currency} {proposal.total_amount:,.2f}"
    )
    if not branding or not branding.logo_reference:
        st.warning("No logo configured. A clean text-based tenant header will be used.")
    if not organization.contact_email and not organization.contact_phone:
        st.warning("Organization contact details are incomplete.")
    if not items:
        st.warning("This proposal has no commercial items.")
    if not sections:
        st.warning("This proposal has no narrative sections.")
    st.subheader("Generate PDF")
    suggested = f"Proposal-{proposal.proposal_number}.pdf"
    file_name = st.text_input("PDF file name", value=suggested, max_chars=190)
    confidential = st.checkbox("Include confidential label", value=True)
    if st.button("Generate PDF", type="primary"):
        _mutate(
            lambda: container.proposal_pdf.generate_proposal_pdf(
                proposal_id,
                file_name=file_name,
                include_confidential_label=confidential,
            ),
            "Proposal PDF generated without changing proposal data.",
        )
    records = container.proposal_pdf.list_proposal_documents(proposal_id)
    ready = tuple(
        document
        for document in records
        if document.status == ProposalDocumentStatus.READY
    )
    st.subheader("Latest PDF")
    if ready:
        latest = ready[0]
        st.caption(
            f"{latest.file_name} · {latest.page_count} pages · "
            f"{latest.file_size_bytes or 0:,} bytes · "
            f"Source {latest.source_snapshot_hash[:12]}"
        )
        _, content = container.proposal_pdf.download_proposal_document(latest.id)
        st.download_button(
            "Download PDF",
            content,
            file_name=latest.file_name,
            mime="application/pdf",
        )
    else:
        st.info("No ready PDF export exists yet.")
    st.subheader("Export History")
    if records:
        st.dataframe(
            [
                {
                    "Document": record.id,
                    "File": record.file_name,
                    "Status": record.status.value,
                    "Created": record.created_at,
                    "Pages": record.page_count,
                    "Size": record.file_size_bytes,
                    "Source hash": record.source_snapshot_hash[:12],
                }
                for record in records
            ],
            hide_index=True,
            width="stretch",
        )


def _proposal_email(container: Container, proposal_id: int) -> None:
    service = container.proposal_email
    proposal = container.proposals.get_proposal(proposal_id)
    ready = tuple(
        document
        for document in container.proposal_pdf.list_proposal_documents(proposal_id)
        if document.status == ProposalDocumentStatus.READY
    )
    st.subheader("Email Readiness")
    st.caption(
        f"{proposal.proposal_number} · {proposal.status.value} · tenant-branded delivery"
    )
    if not service.configured:
        st.warning("Email not configured. Proposal email sending is unavailable.")
    if not ready:
        st.warning(
            "No READY proposal PDF exists. Generate the PDF before composing email."
        )
    config = service.configuration
    if config:
        st.write(
            f"Provider: {config.provider.value} · Sender: {config.from_name} <{config.from_address}>"
        )
    st.subheader("Compose Email")
    labels = {
        document.id: f"{document.file_name} · {(document.file_size_bytes or 0):,} bytes · {document.sha256_checksum[:12] if document.sha256_checksum else 'pending'}"
        for document in ready
    }
    selected = st.selectbox(
        "Select READY PDF", tuple(labels), format_func=labels.get, disabled=not ready
    )
    with st.form(f"proposal_email_compose_{proposal_id}"):
        to_addresses = st.text_input("To", help="Comma-separated addresses")
        cc_addresses = st.text_input("CC", help="Optional, comma-separated addresses")
        bcc_addresses = st.text_input("BCC", help="Optional; masked in preview")
        subject = st.text_input(
            "Subject",
            value=f"Proposal {proposal.proposal_number} – {proposal.title}",
            max_chars=300,
        )
        intro = st.text_area(
            "Introductory message",
            value=f"Please find our proposal for {proposal.company_name} attached for your review.",
            max_chars=5000,
        )
        closing = st.text_area(
            "Closing message",
            value="Please contact us if you have any questions.",
            max_chars=5000,
        )
        save = st.form_submit_button(
            "Save draft", disabled=not service.configured or not ready
        )
    if save and selected:
        try:
            draft = service.create_email_draft(
                proposal_id,
                selected,
                to_addresses=to_addresses,
                cc_addresses=cc_addresses,
                bcc_addresses=bcc_addresses,
                subject=subject,
                intro_message=intro,
                closing_message=closing,
            )
        except EmailError as exc:
            st.error(str(exc))
        else:
            st.session_state[f"proposal_email_draft_{proposal_id}"] = draft.id
            st.success("Email draft saved. Review the preview before sending.")
    delivery_id = st.session_state.get(f"proposal_email_draft_{proposal_id}")
    if delivery_id:
        try:
            preview = service.preview_email_delivery(delivery_id)
        except EmailError as exc:
            st.error(str(exc))
        else:
            st.subheader("Preview")
            st.caption(
                f"From {preview.delivery.from_name} <{preview.delivery.from_address}> · To {', '.join(preview.delivery.recipients.to)} · BCC {', '.join(preview.masked_bcc) or 'None'}"
            )
            st.markdown(preview.delivery.html_body, unsafe_allow_html=True)
            with st.expander("Plain-text preview"):
                st.text(preview.delivery.text_body)
            st.caption(
                f"Attachment: {preview.delivery.attachment_file_name} · {preview.attachment_size:,} bytes · {preview.delivery.attachment_checksum[:12]}"
            )
            confirm = st.checkbox(
                "I confirm the recipients, message, and attached proposal PDF",
                key=f"email_confirm_{delivery_id}",
            )
            if st.button(
                "Send Proposal",
                type="primary",
                disabled=not confirm
                or preview.delivery.status != ProposalEmailDeliveryStatus.DRAFT,
            ):
                _mutate(
                    lambda: service.send_email_delivery(delivery_id),
                    "Proposal email delivery completed.",
                )
    st.subheader("Delivery History")
    deliveries = service.list_email_deliveries(proposal_id)
    if deliveries:
        st.dataframe(
            [
                {
                    "Delivery": item.id,
                    "Created": item.created_at,
                    "Status": item.status.value,
                    "Provider": item.provider.value,
                    "Sender": item.from_address,
                    "To": len(item.recipients.to),
                    "CC": len(item.recipients.cc),
                    "BCC": len(item.recipients.bcc),
                    "Subject": item.subject,
                    "Attachment": item.attachment_file_name,
                    "Attempts": item.attempt_count,
                    "Sent": item.sent_at,
                    "Message ID": item.provider_message_id,
                    "Error": item.safe_error_message,
                }
                for item in deliveries
            ],
            hide_index=True,
            width="stretch",
        )
        latest_delivery = deliveries[0]
        actions = st.columns(3)
        if actions[0].button(
            "Retry Failed Delivery",
            disabled=latest_delivery.status != ProposalEmailDeliveryStatus.FAILED,
            key=f"retry_email_{latest_delivery.id}",
        ):
            _mutate(
                lambda: service.retry_email_delivery(latest_delivery.id),
                "Transient email delivery retried.",
            )
        if actions[1].button(
            "Resend",
            disabled=latest_delivery.status != ProposalEmailDeliveryStatus.SENT,
            key=f"resend_email_{latest_delivery.id}",
        ):
            try:
                resend = service.resend_proposal_email(latest_delivery.id)
            except EmailError as exc:
                st.error(str(exc))
            else:
                st.session_state[f"proposal_email_draft_{proposal_id}"] = resend.id
                st.success("A new immutable resend draft was created.")
                st.rerun()
        if actions[2].button(
            "Cancel Draft",
            disabled=latest_delivery.status
            not in {
                ProposalEmailDeliveryStatus.DRAFT,
                ProposalEmailDeliveryStatus.QUEUED,
            },
            key=f"cancel_email_{latest_delivery.id}",
        ):
            _mutate(
                lambda: service.cancel_email_delivery(latest_delivery.id),
                "Email delivery cancelled.",
            )
