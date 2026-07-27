from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from leadpilot.infrastructure.database.base import Base


class CompanyModel(Base):
    """Database representation of a company lead."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="New", index=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
