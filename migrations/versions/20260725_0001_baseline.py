"""Create the empty Milestone 1 baseline.

Revision ID: 20260725_0001
Revises:
Create Date: 2026-07-25
"""

from typing import Sequence

revision: str = "20260725_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish the baseline without business tables."""


def downgrade() -> None:
    """Remove the empty baseline."""
