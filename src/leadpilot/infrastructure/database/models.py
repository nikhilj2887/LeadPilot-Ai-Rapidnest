from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    discovery_scans: Mapped[list[DiscoveryScanModel]] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )


class DiscoveryScanModel(Base):
    """A persisted snapshot of observable website discovery signals."""

    __tablename__ = "discovery_scans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    website_url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(20), default="Pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    http_status_code: Mapped[int | None] = mapped_column(Integer)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    page_title: Mapped[str | None] = mapped_column(String(500))
    meta_description: Mapped[str | None] = mapped_column(Text)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    is_https: Mapped[bool] = mapped_column(Boolean, default=False)
    ssl_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    mobile_viewport_present: Mapped[bool] = mapped_column(Boolean, default=False)
    robots_txt_present: Mapped[bool] = mapped_column(Boolean, default=False)
    sitemap_present: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_page_present: Mapped[bool] = mapped_column(Boolean, default=False)
    about_page_present: Mapped[bool] = mapped_column(Boolean, default=False)
    careers_page_present: Mapped[bool] = mapped_column(Boolean, default=False)
    blog_present: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_policy_present: Mapped[bool] = mapped_column(Boolean, default=False)
    terms_page_present: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_form_present: Mapped[bool] = mapped_column(Boolean, default=False)
    newsletter_present: Mapped[bool] = mapped_column(Boolean, default=False)
    booking_system_present: Mapped[bool] = mapped_column(Boolean, default=False)
    ecommerce_present: Mapped[bool] = mapped_column(Boolean, default=False)
    live_chat_present: Mapped[bool] = mapped_column(Boolean, default=False)
    chatbot_present: Mapped[bool] = mapped_column(Boolean, default=False)
    whatsapp_present: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_present: Mapped[bool] = mapped_column(Boolean, default=False)
    email_present: Mapped[bool] = mapped_column(Boolean, default=False)
    social_links_present: Mapped[bool] = mapped_column(Boolean, default=False)
    linkedin_present: Mapped[bool] = mapped_column(Boolean, default=False)
    facebook_present: Mapped[bool] = mapped_column(Boolean, default=False)
    instagram_present: Mapped[bool] = mapped_column(Boolean, default=False)
    x_present: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_technologies: Mapped[str] = mapped_column(Text, default="[]")
    detected_emails: Mapped[str] = mapped_column(Text, default="[]")
    detected_phone_numbers: Mapped[str] = mapped_column(Text, default="[]")
    detected_social_links: Mapped[str] = mapped_column(Text, default="[]")
    website_health_score: Mapped[int] = mapped_column(Integer, default=0)
    digital_maturity_score: Mapped[int] = mapped_column(Integer, default=0)
    ai_readiness_score: Mapped[int] = mapped_column(Integer, default=0)
    automation_potential_score: Mapped[int] = mapped_column(Integer, default=0)
    lead_priority_score: Mapped[int] = mapped_column(Integer, default=0)
    score_details: Mapped[str] = mapped_column(Text, default="{}")
    findings: Mapped[str] = mapped_column(Text, default="[]")
    recommendations: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    company: Mapped[CompanyModel] = relationship(back_populates="discovery_scans")
