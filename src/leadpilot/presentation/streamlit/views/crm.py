from __future__ import annotations

from decimal import Decimal

import streamlit as st

from leadpilot.application.auth import AuthorizationError
from leadpilot.application.crm import CrmError
from leadpilot.bootstrap import Container
from leadpilot.presentation.streamlit.components import page_header


def render(container: Container) -> None:
    page_header(
        "CRM",
        "Manage contacts, leads, opportunities, follow-ups, and sales history.",
        eyebrow="Sales workspace",
    )
    overview, leads, opportunities, contacts, activities, tasks, intelligence = st.tabs(
        (
            "Overview",
            "Leads",
            "Opportunities",
            "Contacts",
            "Activities & Notes",
            "Tasks",
            "Sales Intelligence",
        )
    )
    with overview:
        _overview(container)
    with leads:
        _leads(container)
    with opportunities:
        _opportunities(container)
    with contacts:
        _contacts(container)
    with activities:
        _activities(container)
    with tasks:
        _tasks(container)
    with intelligence:
        _sales_intelligence(container)


def _sales_intelligence(container: Container) -> None:
    st.subheader("Sales Intelligence")
    st.caption(
        "Deterministic scores and forecasts with reviewable recommendations. "
        "No CRM record is changed automatically."
    )
    (
        summary,
        lead_tab,
        health_tab,
        follow_up,
        risk_tab,
        forecast_tab,
        analysis_tab,
        history,
    ) = st.tabs(
        (
            "Executive Summary",
            "Lead Priorities",
            "Opportunity Health",
            "Follow-Up Queue",
            "Pipeline Risk",
            "Revenue Forecast",
            "Win/Loss & Team",
            "Recommendation History",
        )
    )
    recommendations = container.sales_intelligence.list_recommendations(page_size=500)
    forecasts = container.sales_intelligence.repo.list_forecasts()
    with summary:
        risks = container.sales_intelligence.pipeline_risks()
        values = (
            ("Pending recommendations", recommendations.total),
            ("Pipeline risks", len(risks)),
            ("Forecast snapshots", len(forecasts)),
            ("Automation", "Human approved"),
        )
        for column, (label, value) in zip(st.columns(4), values, strict=True):
            column.metric(label, value)
        if risks:
            st.bar_chart(
                {row["risk_type"]: float(row["amount_affected"]) for row in risks}
            )
        else:
            st.info("No pipeline risks are currently available.")
    with lead_tab:
        leads = container.crm.list("lead", page_size=500).items
        if st.button("Recalculate lead priorities"):
            _action(
                container.sales_intelligence.calculate_all_lead_priorities,
                "Lead priorities recalculated.",
            )
        st.dataframe(
            [
                {
                    "Lead": x.lead_number,
                    "Title": x.title,
                    "Qualification score": x.score,
                    "Current priority": x.priority,
                    "Next follow-up": x.next_follow_up_at,
                }
                for x in leads
            ],
            hide_index=True,
            width="stretch",
        )
    with health_tab:
        opportunities = container.crm.list("opportunity", page_size=500).items
        if st.button("Recalculate opportunity health"):
            _action(
                container.sales_intelligence.calculate_all_health_scores,
                "Opportunity health recalculated.",
            )
        st.dataframe(
            [
                {
                    "Opportunity": x.opportunity_number,
                    "Name": x.name,
                    "Status": x.status,
                    "Amount": x.amount,
                    "Probability": x.probability_percentage,
                    "Close date": x.expected_close_date,
                }
                for x in opportunities
            ],
            hide_index=True,
            width="stretch",
        )
    with follow_up:
        pending = [
            x
            for x in recommendations.items
            if x.recommendation_type in {"FOLLOW_UP", "CALL", "CREATE_TASK"}
        ]
        if pending:
            st.dataframe(
                [
                    {
                        "Entity": x.entity_type,
                        "Type": x.recommendation_type,
                        "Priority": x.priority,
                        "Title": x.title,
                        "Status": x.status,
                        "Due": x.suggested_due_at,
                    }
                    for x in pending
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No follow-up recommendations need review.")
        pending_review = [
            item for item in recommendations.items if item.status == "PENDING_REVIEW"
        ]
        if pending_review:
            selected = st.selectbox(
                "Recommendation to review",
                pending_review,
                format_func=lambda item: f"{item.priority} · {item.title}",
            )
            approve, reject = st.columns(2)
            if approve.button("Approve recommendation"):
                _action(
                    lambda: container.sales_intelligence.approve_recommendation(
                        selected.id
                    ),
                    "Recommendation approved. Apply remains a separate action.",
                )
            if reject.button("Reject recommendation"):
                _action(
                    lambda: container.sales_intelligence.reject_recommendation(
                        selected.id
                    ),
                    "Recommendation rejected.",
                )
    with risk_tab:
        risks = container.sales_intelligence.pipeline_risks()
        st.dataframe(risks, hide_index=True, width="stretch") if risks else st.info(
            "No pipeline risk data is available."
        )
    with forecast_tab:
        start = st.date_input("Forecast start")
        end = st.date_input(
            "Forecast end",
            value=start.replace(year=start.year + 1)
            if start.month != 2 or start.day != 29
            else start,
        )
        method = st.selectbox(
            "Forecast method",
            ("STAGE_WEIGHTED", "MANAGER_COMMIT", "BEST_CASE", "WORST_CASE", "SCENARIO"),
        )
        adjustment = st.number_input(
            "Scenario probability adjustment",
            min_value=-100,
            max_value=100,
            value=0,
            disabled=method != "SCENARIO",
        )
        if st.button("Generate forecast"):
            _action(
                lambda: container.sales_intelligence.generate_forecast(
                    start,
                    end,
                    method,
                    {"probability_adjustment": adjustment}
                    if method == "SCENARIO"
                    else None,
                ),
                "Forecast generated.",
            )
        if forecasts:
            st.dataframe(
                [
                    {
                        "Date": x.forecast_date,
                        "Period": f"{x.period_start} – {x.period_end}",
                        "Method": x.forecast_method,
                        "Currency": x.currency,
                        "Pipeline": x.open_pipeline_amount,
                        "Weighted": x.weighted_pipeline_amount,
                        "Commit": x.commit_amount,
                        "Best case": x.best_case_amount,
                        "Worst case": x.worst_case_amount,
                    }
                    for x in forecasts
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No forecast snapshots have been generated.")
    with analysis_tab:
        st.write("Team performance")
        try:
            team = container.sales_intelligence.team_metrics()
        except AuthorizationError:
            team = ()
        st.dataframe(team, hide_index=True, width="stretch") if team else st.info(
            "Insufficient data for team performance metrics."
        )
        st.caption("Win/loss analyses become available after opportunities are closed.")
    with history:
        if recommendations.items:
            st.dataframe(
                [
                    {
                        "Reference": f"REC-{x.id:06d}",
                        "Entity": x.entity_type,
                        "Type": x.recommendation_type,
                        "Priority": x.priority,
                        "Status": x.status,
                        "Title": x.title,
                        "Created": x.created_at,
                    }
                    for x in recommendations.items
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No recommendation history is available.")


def _overview(container: Container) -> None:
    metrics = container.crm.metrics()
    lead_counts = metrics["leads"]
    values = (
        ("New leads", lead_counts.get("NEW", 0)),
        ("Assigned", lead_counts.get("ASSIGNED", 0)),
        ("Qualified", lead_counts.get("QUALIFIED", 0)),
        ("Open opportunities", metrics["open_opportunities"]),
        ("Pipeline value", metrics["pipeline_value"]),
        ("Weighted pipeline", metrics["weighted_pipeline"]),
        ("Upcoming tasks", metrics["upcoming_tasks"]),
        ("Overdue tasks", metrics["overdue_tasks"]),
    )
    for row in (values[:4], values[4:]):
        for column, (label, value) in zip(st.columns(4), row, strict=True):
            column.metric(label, value)
    charts = st.columns(2)
    charts[0].bar_chart(lead_counts)
    opportunities = container.crm.list("opportunity", page_size=500).items
    stage_values: dict[str, float] = {}
    for item in opportunities:
        stage_label = str(item.status).replace("_", " ").title()
        stage_values[stage_label] = stage_values.get(stage_label, 0) + float(
            item.weighted_amount
        )
    charts[1].bar_chart(stage_values)
    query = st.text_input("Global CRM search")
    if query:
        results = container.crm.search(query)
        for group, items in results.items():
            st.write(f"**{group.title()}**")
            st.write(
                [
                    getattr(item, "title", None)
                    or getattr(item, "name", None)
                    or f"{item.first_name} {item.last_name}"
                    for item in items
                ]
            )


def _leads(container: Container) -> None:
    companies = {item.id: item.name for item in container.companies.list_companies()}
    query = st.text_input("Search leads")
    status = st.selectbox(
        "Lead status",
        (
            None,
            "NEW",
            "ASSIGNED",
            "CONTACTED",
            "NURTURING",
            "QUALIFIED",
            "DISQUALIFIED",
            "CONVERTED",
            "ARCHIVED",
        ),
    )
    page = container.crm.list("lead", query=query, status=status)
    st.dataframe(
        [
            {
                "Lead": x.lead_number,
                "Title": x.title,
                "Source": x.source,
                "Status": x.status,
                "Qualification": x.qualification_status,
                "Priority": x.priority,
                "Score": x.score,
                "Value": x.estimated_value,
            }
            for x in page.items
        ],
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Export filtered leads",
        container.crm.export_csv("lead", query=query, status=status),
        "leads.csv",
        "text/csv",
    )
    with st.expander("Create lead"):
        with st.form("crm_lead_create"):
            title = st.text_input("Lead title")
            company = st.selectbox(
                "Company (optional)",
                (None, *companies),
                format_func=lambda value: companies.get(value, "Standalone"),
            )
            source = st.selectbox(
                "Source",
                (
                    "MANUAL",
                    "DISCOVERY",
                    "REFERRAL",
                    "WEBSITE",
                    "EVENT",
                    "PARTNER",
                    "EMAIL",
                    "LINKEDIN",
                    "OTHER",
                ),
            )
            priority = st.selectbox("Priority", ("LOW", "MEDIUM", "HIGH", "URGENT"))
            value = st.number_input("Estimated value", min_value=0.0)
            submit = st.form_submit_button("Create lead")
        if submit:
            _action(
                lambda: container.crm.create_lead(
                    title,
                    company_id=company,
                    source=source,
                    priority=priority,
                    estimated_value=Decimal(str(value)),
                ),
                "Lead created.",
            )
    _csv_import(container)


def _csv_import(container: Container) -> None:
    with st.expander("CSV lead import"):
        upload = st.file_uploader("Lead CSV", type=("csv",))
        if upload:
            try:
                preview = container.crm.preview_csv(upload.getvalue())
            except CrmError as exc:
                st.error(str(exc))
                return
            st.write(
                f"{len(preview.valid_rows)} valid rows · {len(preview.errors)} errors"
            )
            if preview.errors:
                st.warning("\n".join(preview.errors))
            st.dataframe(preview.valid_rows, hide_index=True)
            confirmed = st.checkbox("Confirm import of valid rows")
            if st.button("Import leads", disabled=not confirmed):
                _action(
                    lambda: container.crm.import_csv(upload.getvalue(), dry_run=False),
                    "CSV import completed.",
                )


def _opportunities(container: Container) -> None:
    companies = {item.id: item.name for item in container.companies.list_companies()}
    page = container.crm.list("opportunity")
    st.dataframe(
        [
            {
                "Opportunity": x.opportunity_number,
                "Name": x.name,
                "Status": x.status,
                "Amount": x.amount,
                "Probability": x.probability_percentage,
                "Weighted": x.weighted_amount,
                "Close": x.expected_close_date,
            }
            for x in page.items
        ],
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Export opportunities",
        container.crm.export_csv("opportunity"),
        "opportunities.csv",
        "text/csv",
    )
    if companies:
        with st.form("crm_opportunity_create"):
            name = st.text_input("Opportunity name")
            company = st.selectbox(
                "Company", tuple(companies), format_func=companies.__getitem__
            )
            amount = st.number_input("Amount", min_value=0.0)
            currency = st.text_input("Currency", "INR", max_chars=3)
            create = st.form_submit_button("Create opportunity")
        if create:
            _action(
                lambda: container.crm.create_opportunity(
                    company, name, Decimal(str(amount)), currency
                ),
                "Opportunity created.",
            )


def _contacts(container: Container) -> None:
    companies = {item.id: item.name for item in container.companies.list_companies()}
    page = container.crm.list("contact")
    st.dataframe(
        [
            {
                "Name": f"{x.first_name} {x.last_name}",
                "Email": x.email,
                "Phone": x.phone,
                "Primary": x.is_primary,
                "Status": x.status,
            }
            for x in page.items
        ],
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Export contacts",
        container.crm.export_csv("contact"),
        "contacts.csv",
        "text/csv",
    )
    if companies:
        with st.form("crm_contact_create"):
            company = st.selectbox(
                "Company", tuple(companies), format_func=companies.__getitem__
            )
            first = st.text_input("First name")
            last = st.text_input("Last name")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            primary = st.checkbox("Primary contact")
            create = st.form_submit_button("Create contact")
        if create:
            _action(
                lambda: container.crm.create_contact(
                    company, first, last, email=email, phone=phone, is_primary=primary
                ),
                "Contact created.",
            )


def _activities(container: Container) -> None:
    lead_page = container.crm.list("lead", page_size=500)
    leads = {item.id: f"{item.lead_number} · {item.title}" for item in lead_page.items}
    st.dataframe(
        [
            {
                "Subject": x.subject,
                "Type": x.activity_type,
                "Status": x.status,
                "Scheduled": x.scheduled_at,
                "Completed": x.completed_at,
            }
            for x in container.crm.list("activity").items
        ],
        hide_index=True,
        width="stretch",
    )
    if leads:
        with st.form("activity_create"):
            lead = st.selectbox(
                "Related lead", tuple(leads), format_func=leads.__getitem__
            )
            subject = st.text_input("Activity subject")
            activity_type = st.selectbox(
                "Activity type",
                ("CALL", "EMAIL", "MEETING", "DEMO", "FOLLOW_UP", "NOTE", "PROPOSAL"),
            )
            create = st.form_submit_button("Create activity")
        if create:
            _action(
                lambda: container.crm.create_related(
                    "activity", subject, {"lead_id": lead}, activity_type=activity_type
                ),
                "Activity created.",
            )
        with st.form("note_create"):
            note_lead = st.selectbox(
                "Note lead", tuple(leads), format_func=leads.__getitem__
            )
            content = st.text_area("Note")
            pinned = st.checkbox("Pin note")
            add = st.form_submit_button("Add note")
        if add:
            _action(
                lambda: container.crm.create_related(
                    "note", content, {"lead_id": note_lead}, is_pinned=pinned
                ),
                "Note added.",
            )


def _tasks(container: Container) -> None:
    tasks = container.crm.list("task").items
    st.dataframe(
        [
            {
                "Task": x.title,
                "Priority": x.priority,
                "Status": x.status,
                "Due": x.due_at,
                "Completed": x.completed_at,
            }
            for x in tasks
        ],
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Export tasks", container.crm.export_csv("task"), "tasks.csv", "text/csv"
    )
    leads = {
        item.id: item.title for item in container.crm.list("lead", page_size=500).items
    }
    if leads:
        with st.form("task_create"):
            lead = st.selectbox(
                "Task lead", tuple(leads), format_func=leads.__getitem__
            )
            title = st.text_input("Task title")
            priority = st.selectbox(
                "Task priority", ("LOW", "MEDIUM", "HIGH", "URGENT")
            )
            create = st.form_submit_button("Create task")
        if create:
            _action(
                lambda: container.crm.create_related(
                    "task", title, {"lead_id": lead}, priority=priority
                ),
                "Task created.",
            )


def _action(operation: object, message: str) -> None:
    try:
        operation()  # type: ignore[operator]
    except (CrmError, PermissionError) as exc:
        st.error(str(exc))
    else:
        st.success(message)
        st.rerun()
