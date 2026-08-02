from __future__ import annotations

from datetime import UTC, datetime

from leadpilot.application.proposal_portal import (
    ProposalPortalAccessContext,
    ProposalPortalLink,
    ProposalPortalLinkStatus,
)


def build_acceptance_context(
    organization_id: int = 1,
) -> ProposalPortalAccessContext:
    """Build an active portal context shared by proposal workflow tests."""
    link = ProposalPortalLink(
        7,
        organization_id,
        11,
        13,
        ProposalPortalLinkStatus.ACTIVE,
        "hash",
        "prefix",
        None,
        False,
        None,
        None,
        0,
        True,
        True,
        None,
        None,
        datetime.now(UTC),
        datetime.now(UTC),
        None,
        None,
        None,
    )
    return ProposalPortalAccessContext(link, "request")
