from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from leadpilot.application.proposal_engagement import (
    EngagementEvent,
    EngagementEventType,
    ProposalEngagementService,
)
from leadpilot.application.proposal_portal import ProposalPortalAccessContext
from tests.test_support import build_acceptance_context


class Repository:
    def __init__(self, events: tuple[EngagementEvent, ...] = ()) -> None:
        self.events = list(events)
        self.values: dict[str, object] = {}

    def create_event(self, context: ProposalPortalAccessContext, values):
        self.values = values
        event = EngagementEvent(
            len(self.events) + 1,
            context.link.organization_id,
            context.link.proposal_id,
            context.link.id,
            context.link.proposal_document_id,
            str(values["visitor_id"]),
            str(values["session_id"]),
            EngagementEventType(str(values["event_type"])),
            values["page_number"],
            values["section_key"],
            values["duration_ms"],
            {},
            values["ip_hash"],
            values["user_agent_hash"],
            datetime.now(UTC),
        )
        self.events.append(event)
        return event

    def list_by_proposal(self, proposal_id: int):
        return tuple(
            event
            for event in self.events
            if not proposal_id or event.proposal_id == proposal_id
        )

    def organization_status_counts(self):
        return {"SENT": 2, "ACCEPTED": 1, "REJECTED": 1, "EXPIRED": 1}

    def proposal_count(self):
        return 4

    def purge_before(self, cutoff: datetime):
        original = len(self.events)
        self.events = [item for item in self.events if item.created_at >= cutoff]
        return original - len(self.events)


def event(
    event_type: EngagementEventType,
    *,
    visitor: str = "visitor-a",
    session: str = "session-a",
    section: str | None = None,
    duration: int | None = None,
    created: datetime | None = None,
    proposal_id: int = 11,
) -> EngagementEvent:
    return EngagementEvent(
        1,
        1,
        proposal_id,
        7,
        13,
        visitor,
        session,
        event_type,
        None,
        section,
        duration,
        {},
        "ip-hash",
        "agent-hash",
        created or datetime.now(UTC),
    )


def test_tracking_hashes_anonymous_and_request_values() -> None:
    repository = Repository()
    service = ProposalEngagementService(repository, "pepper")
    tracked = service.track(
        build_acceptance_context(),
        EngagementEventType.PAGE_VIEWED,
        visitor_id="visitor-raw",
        session_id="session-raw",
        page_number=2,
        ip_address="192.0.2.1",
        user_agent="browser-raw",
        metadata={"source": "portal", "secret": "discard"},
    )
    assert tracked.event_type == EngagementEventType.PAGE_VIEWED
    assert repository.values["visitor_id"] != "visitor-raw"
    assert repository.values["session_id"] != "session-raw"
    assert repository.values["ip_hash"] != "192.0.2.1"
    assert repository.values["user_agent_hash"] != "browser-raw"
    assert "secret" not in str(repository.values["metadata_json"])


@pytest.mark.parametrize(
    "values",
    [
        {"visitor_id": ""},
        {"session_id": ""},
        {"page_number": 0},
        {"duration_ms": -1},
        {"duration_ms": 86_400_001},
    ],
)
def test_tracking_rejects_invalid_values(values) -> None:
    service = ProposalEngagementService(Repository(), "pepper")
    defaults = {"visitor_id": "visitor", "session_id": "session"}
    with pytest.raises(ValueError):
        service.track(
            build_acceptance_context(),
            EngagementEventType.PROPOSAL_VIEWED,
            **{**defaults, **values},
        )


def test_metrics_calculate_views_visitors_returns_sessions_and_downloads() -> None:
    events = (
        event(EngagementEventType.PROPOSAL_VIEWED),
        event(EngagementEventType.PROPOSAL_VIEWED, session="session-b"),
        event(
            EngagementEventType.PROPOSAL_VIEWED,
            visitor="visitor-b",
            session="session-c",
        ),
        event(EngagementEventType.PDF_DOWNLOADED),
        event(EngagementEventType.PAGE_VIEWED),
        event(EngagementEventType.SECTION_VIEWED, section="pricing"),
    )
    metrics = (
        ProposalEngagementService(Repository(events), "pepper")
        .proposal_analytics(11)
        .metrics
    )
    assert (metrics.total_views, metrics.unique_visitors, metrics.return_visitors) == (
        3,
        2,
        1,
    )
    assert (metrics.total_sessions, metrics.downloads, metrics.pages_viewed) == (
        3,
        1,
        1,
    )


def test_session_duration_average_and_longest() -> None:
    events = (
        event(EngagementEventType.TIME_ON_PAGE, duration=1000),
        event(EngagementEventType.TIME_ON_SECTION, duration=3000),
        event(EngagementEventType.TIME_ON_PAGE, session="session-b", duration=2000),
    )
    metrics = (
        ProposalEngagementService(Repository(events), "pepper")
        .proposal_analytics(11)
        .metrics
    )
    assert metrics.average_time_ms == 3000
    assert metrics.longest_session_ms == 4000


def test_heatmap_combines_section_views_and_time() -> None:
    events = (
        event(EngagementEventType.SECTION_VIEWED, section="pricing"),
        event(EngagementEventType.SECTION_VIEWED, section="pricing"),
        event(EngagementEventType.TIME_ON_SECTION, section="pricing", duration=5000),
    )
    analytics = ProposalEngagementService(
        Repository(events), "pepper"
    ).proposal_analytics(11)
    assert analytics.heatmap == (("pricing", 2, 5000),)
    assert "Pricing reviewed multiple times." in analytics.insights


def test_timeline_is_chronological_repository_order() -> None:
    now = datetime.now(UTC)
    events = (
        event(EngagementEventType.PORTAL_OPENED, created=now),
        event(EngagementEventType.PDF_DOWNLOADED, created=now + timedelta(seconds=5)),
        event(EngagementEventType.ACCEPTED, created=now + timedelta(seconds=10)),
    )
    timeline = (
        ProposalEngagementService(Repository(events), "pepper")
        .proposal_analytics(11)
        .timeline
    )
    assert [item.event_type for item in timeline] == [
        EngagementEventType.PORTAL_OPENED,
        EngagementEventType.PDF_DOWNLOADED,
        EngagementEventType.ACCEPTED,
    ]


def test_acceptance_rate_and_time_before_acceptance() -> None:
    now = datetime.now(UTC)
    events = (
        event(EngagementEventType.PROPOSAL_VIEWED, created=now),
        event(EngagementEventType.ACCEPTED, created=now + timedelta(minutes=5)),
        event(EngagementEventType.REJECTED, visitor="visitor-b"),
    )
    metrics = (
        ProposalEngagementService(Repository(events), "pepper")
        .proposal_analytics(11)
        .metrics
    )
    assert metrics.acceptance_rate == 50
    assert metrics.average_time_before_acceptance_ms == 300_000


def test_time_and_download_charts_group_by_date_and_hour() -> None:
    now = datetime(2026, 8, 2, 14, tzinfo=UTC)
    events = (
        event(EngagementEventType.PROPOSAL_VIEWED, created=now),
        event(EngagementEventType.PROPOSAL_VIEWED, created=now),
        event(EngagementEventType.PDF_DOWNLOADED, created=now),
    )
    analytics = ProposalEngagementService(
        Repository(events), "pepper"
    ).proposal_analytics(11)
    assert analytics.daily_views == (("2026-08-02", 2),)
    assert analytics.views_by_hour == ((14, 2),)
    assert analytics.downloads_by_day == (("2026-08-02", 1),)


def test_csv_export_is_scoped_and_contains_no_raw_network_values() -> None:
    repository = Repository((event(EngagementEventType.PROPOSAL_VIEWED),))
    content = ProposalEngagementService(repository, "pepper").export_csv(11)
    rows = list(csv.DictReader(io.StringIO(content.decode())))
    assert rows[0]["event"] == "PROPOSAL_VIEWED"
    assert "ip-hash" not in content.decode()
    assert "agent-hash" not in content.decode()


def test_export_requires_authorization_and_audits_download() -> None:
    calls: list[str] = []
    service = ProposalEngagementService(
        Repository(),
        "pepper",
        lambda: calls.append("authorized"),
        lambda action, *_: calls.append(action),
    )
    service.audit_export(11)
    assert calls == ["authorized", "ENGAGEMENT_EXPORTED"]


def test_purge_is_scoped_by_repository_and_audited() -> None:
    calls: list[str] = []
    old = event(
        EngagementEventType.PORTAL_OPENED,
        created=datetime.now(UTC) - timedelta(days=90),
    )
    service = ProposalEngagementService(
        Repository((old,)),
        "pepper",
        lambda: calls.append("authorized"),
        lambda action, *_: calls.append(action),
    )
    assert service.purge_before(datetime.now(UTC) - timedelta(days=30)) == 1
    assert calls == ["authorized", "ENGAGEMENT_PURGED"]


def test_authorization_failure_blocks_analytics() -> None:
    def denied() -> None:
        raise PermissionError("denied")

    service = ProposalEngagementService(Repository(), "pepper", denied)
    with pytest.raises(PermissionError):
        service.proposal_analytics(11)


def test_organization_metrics_are_tenant_repository_rollups() -> None:
    events = (
        event(EngagementEventType.PROPOSAL_VIEWED),
        event(EngagementEventType.PROPOSAL_VIEWED, proposal_id=12),
        event(EngagementEventType.PDF_DOWNLOADED),
    )
    metrics = ProposalEngagementService(
        Repository(events), "pepper"
    ).organization_metrics()
    assert (metrics.proposals_sent, metrics.viewed, metrics.downloaded) == (2, 2, 1)
    assert (metrics.accepted, metrics.rejected, metrics.expired) == (1, 1, 1)
    assert metrics.average_views == 0.5


def test_ui_exposes_heatmap_timeline_charts_and_csv_without_internal_paths() -> None:
    source = Path("src/leadpilot/presentation/streamlit/views/proposals.py").read_text()
    assert all(
        label in source
        for label in ("Section heatmap", "Engagement timeline", "Export analytics CSV")
    )
    assert "storage_key" not in source
