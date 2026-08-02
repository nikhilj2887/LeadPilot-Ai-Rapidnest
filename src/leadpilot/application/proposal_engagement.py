from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from statistics import mean
from typing import Protocol

from leadpilot.application.proposal_portal import ProposalPortalAccessContext


class EngagementEventType(StrEnum):
    PORTAL_OPENED = "PORTAL_OPENED"
    PROPOSAL_VIEWED = "PROPOSAL_VIEWED"
    PAGE_VIEWED = "PAGE_VIEWED"
    SECTION_VIEWED = "SECTION_VIEWED"
    TIME_ON_PAGE = "TIME_ON_PAGE"
    TIME_ON_SECTION = "TIME_ON_SECTION"
    PDF_DOWNLOADED = "PDF_DOWNLOADED"
    SIGNATURE_STARTED = "SIGNATURE_STARTED"
    SIGNATURE_COMPLETED = "SIGNATURE_COMPLETED"
    ACCEPT_CLICKED = "ACCEPT_CLICKED"
    REJECT_CLICKED = "REJECT_CLICKED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PORTAL_CLOSED = "PORTAL_CLOSED"


@dataclass(frozen=True, slots=True)
class EngagementEvent:
    id: int
    organization_id: int
    proposal_id: int
    portal_link_id: int
    proposal_document_id: int | None
    visitor_hash: str
    session_hash: str
    event_type: EngagementEventType
    page_number: int | None
    section_key: str | None
    duration_ms: int | None
    metadata: dict[str, object]
    ip_hash: str | None
    user_agent_hash: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EngagementMetrics:
    total_views: int
    unique_visitors: int
    return_visitors: int
    average_time_ms: int
    longest_session_ms: int
    total_sessions: int
    pages_viewed: int
    sections_viewed: int
    downloads: int
    acceptance_rate: float
    average_time_before_acceptance_ms: int


@dataclass(frozen=True, slots=True)
class OrganizationEngagementMetrics:
    proposals_sent: int
    viewed: int
    downloaded: int
    accepted: int
    rejected: int
    expired: int
    average_acceptance_time_ms: int
    average_views: float
    average_downloads: float


@dataclass(frozen=True, slots=True)
class ProposalEngagementAnalytics:
    metrics: EngagementMetrics
    heatmap: tuple[tuple[str, int, int], ...]
    timeline: tuple[EngagementEvent, ...]
    insights: tuple[str, ...]
    daily_views: tuple[tuple[str, int], ...]
    views_by_hour: tuple[tuple[int, int], ...]
    downloads_by_day: tuple[tuple[str, int], ...]


class EngagementRepository(Protocol):
    def create_event(
        self, context: ProposalPortalAccessContext, values: dict[str, object]
    ) -> EngagementEvent: ...
    def list_by_proposal(self, proposal_id: int) -> tuple[EngagementEvent, ...]: ...
    def organization_status_counts(self) -> dict[str, int]: ...
    def proposal_count(self) -> int: ...
    def purge_before(self, cutoff: datetime) -> int: ...


class ProposalEngagementService:
    def __init__(
        self,
        repository: EngagementRepository,
        pepper: str,
        authorize: object = None,
        audit: object = None,
    ) -> None:
        self._repository, self._pepper = repository, pepper
        self._authorize, self._audit = authorize, audit

    def track(
        self,
        context: ProposalPortalAccessContext,
        event_type: EngagementEventType,
        *,
        visitor_id: str,
        session_id: str,
        page_number: int | None = None,
        section_key: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, object] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> EngagementEvent:
        if not visitor_id or not session_id:
            raise ValueError("Anonymous visitor and session identifiers are required.")
        if page_number is not None and page_number < 1:
            raise ValueError("Page number must be positive.")
        if duration_ms is not None and not 0 <= duration_ms <= 86_400_000:
            raise ValueError("Engagement duration is invalid.")
        safe_metadata = {
            key: value
            for key, value in (metadata or {}).items()
            if key in {"source", "action"} and isinstance(value, (str, int, bool))
        }
        return self._repository.create_event(
            context,
            {
                "visitor_id": self._hash(visitor_id),
                "session_id": self._hash(session_id),
                "event_type": event_type.value,
                "page_number": page_number,
                "section_key": section_key[:100] if section_key else None,
                "duration_ms": duration_ms,
                "metadata_json": json.dumps(safe_metadata, sort_keys=True),
                "ip_hash": self._hash(ip_address),
                "user_agent_hash": self._hash(user_agent),
            },
        )

    def proposal_analytics(self, proposal_id: int) -> ProposalEngagementAnalytics:
        self._read()
        events = self._repository.list_by_proposal(proposal_id)
        sessions: dict[str, list[EngagementEvent]] = defaultdict(list)
        visitors: dict[str, set[str]] = defaultdict(set)
        for event in events:
            sessions[event.session_hash].append(event)
            visitors[event.visitor_hash].add(event.session_hash)
        durations = [
            sum(event.duration_ms or 0 for event in values)
            for values in sessions.values()
        ]
        views = sum(
            event.event_type == EngagementEventType.PROPOSAL_VIEWED for event in events
        )
        downloads = sum(
            event.event_type == EngagementEventType.PDF_DOWNLOADED for event in events
        )
        accepted = [
            event
            for event in events
            if event.event_type == EngagementEventType.ACCEPTED
        ]
        rejected = [
            event
            for event in events
            if event.event_type == EngagementEventType.REJECTED
        ]
        acceptance_times = self._acceptance_times(events)
        heatmap_counts: Counter[str] = Counter()
        heatmap_time: Counter[str] = Counter()
        for event in events:
            if (
                event.section_key
                and event.event_type == EngagementEventType.SECTION_VIEWED
            ):
                heatmap_counts[event.section_key] += 1
            if (
                event.section_key
                and event.event_type == EngagementEventType.TIME_ON_SECTION
            ):
                heatmap_time[event.section_key] += event.duration_ms or 0
        heatmap = tuple(
            (key, heatmap_counts[key], heatmap_time[key])
            for key in sorted(set(heatmap_counts) | set(heatmap_time))
        )
        metrics = EngagementMetrics(
            views,
            len(visitors),
            sum(len(value) > 1 for value in visitors.values()),
            int(mean(durations)) if durations else 0,
            max(durations, default=0),
            len(sessions),
            sum(
                event.event_type == EngagementEventType.PAGE_VIEWED for event in events
            ),
            sum(
                event.event_type == EngagementEventType.SECTION_VIEWED
                for event in events
            ),
            downloads,
            round(100 * len(accepted) / max(len(accepted) + len(rejected), 1), 2),
            int(mean(acceptance_times)) if acceptance_times else 0,
        )
        dates = Counter(
            event.created_at.date().isoformat()
            for event in events
            if event.event_type == EngagementEventType.PROPOSAL_VIEWED
        )
        hours = Counter(
            event.created_at.hour
            for event in events
            if event.event_type == EngagementEventType.PROPOSAL_VIEWED
        )
        download_dates = Counter(
            event.created_at.date().isoformat()
            for event in events
            if event.event_type == EngagementEventType.PDF_DOWNLOADED
        )
        return ProposalEngagementAnalytics(
            metrics,
            heatmap,
            events,
            self._insights(metrics, heatmap),
            tuple(sorted(dates.items())),
            tuple(sorted(hours.items())),
            tuple(sorted(download_dates.items())),
        )

    def organization_metrics(self) -> OrganizationEngagementMetrics:
        self._read()
        counts = self._repository.organization_status_counts()
        total = self._repository.proposal_count()
        all_events = self._repository.list_by_proposal(0)
        views = sum(
            event.event_type == EngagementEventType.PROPOSAL_VIEWED
            for event in all_events
        )
        downloads = sum(
            event.event_type == EngagementEventType.PDF_DOWNLOADED
            for event in all_events
        )
        acceptance_times = self._acceptance_times(all_events)
        viewed_proposals = {
            event.proposal_id
            for event in all_events
            if event.event_type == EngagementEventType.PROPOSAL_VIEWED
        }
        downloaded_proposals = {
            event.proposal_id
            for event in all_events
            if event.event_type == EngagementEventType.PDF_DOWNLOADED
        }
        return OrganizationEngagementMetrics(
            counts.get("SENT", 0),
            len(viewed_proposals),
            len(downloaded_proposals),
            counts.get("ACCEPTED", 0),
            counts.get("REJECTED", 0),
            counts.get("EXPIRED", 0),
            int(mean(acceptance_times)) if acceptance_times else 0,
            round(views / max(total, 1), 2),
            round(downloads / max(total, 1), 2),
        )

    def export_csv(self, proposal_id: int) -> bytes:
        self._read()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            (
                "timestamp",
                "event",
                "visitor",
                "session",
                "page",
                "section",
                "duration_ms",
            )
        )
        for event in self._repository.list_by_proposal(proposal_id):
            writer.writerow(
                (
                    event.created_at.isoformat(),
                    event.event_type.value,
                    event.visitor_hash[:12],
                    event.session_hash[:12],
                    event.page_number or "",
                    event.section_key or "",
                    event.duration_ms or "",
                )
            )
        return output.getvalue().encode("utf-8")

    def audit_export(self, proposal_id: int) -> None:
        self._read()
        if self._audit:
            self._audit("ENGAGEMENT_EXPORTED", "proposal", str(proposal_id))

    def purge_before(self, cutoff: datetime) -> int:
        self._read()
        count = self._repository.purge_before(cutoff)
        if self._audit:
            self._audit("ENGAGEMENT_PURGED", "proposal_engagement", str(count))
        return count

    def _read(self) -> None:
        if self._authorize:
            self._authorize()

    def _hash(self, value: str | None) -> str | None:
        return (
            hashlib.sha256(f"{self._pepper}:{value}".encode()).hexdigest()
            if value
            else None
        )

    @staticmethod
    def _acceptance_times(events: tuple[EngagementEvent, ...]) -> list[int]:
        first_views: dict[str, datetime] = {}
        result: list[int] = []
        for event in events:
            if event.event_type == EngagementEventType.PROPOSAL_VIEWED:
                first_views.setdefault(event.visitor_hash, event.created_at)
            elif (
                event.event_type == EngagementEventType.ACCEPTED
                and event.visitor_hash in first_views
            ):
                result.append(
                    max(
                        0,
                        int(
                            (
                                event.created_at - first_views[event.visitor_hash]
                            ).total_seconds()
                            * 1000
                        ),
                    )
                )
        return result

    @staticmethod
    def _insights(
        metrics: EngagementMetrics, heatmap: tuple[tuple[str, int, int], ...]
    ) -> tuple[str, ...]:
        insights: list[str] = []
        sections = {key: views for key, views, _ in heatmap}
        if sections.get("pricing", 0) > 1:
            insights.append("Pricing reviewed multiple times.")
        if heatmap and not sections.get("timeline"):
            insights.append("Timeline never viewed.")
        if metrics.downloads:
            insights.append("Proposal downloaded.")
        if metrics.return_visitors:
            insights.append("Client returned across multiple sessions.")
        if metrics.longest_session_ms >= 600_000:
            insights.append("Viewed for over ten minutes.")
        return tuple(insights)
