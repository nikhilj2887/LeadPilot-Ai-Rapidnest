from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from leadpilot.infrastructure.database.base import Base


class OrganizationModel(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    default_currency: Mapped[str] = mapped_column(String(3), default="INR")
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Kolkata")
    website: Mapped[str | None] = mapped_column(String(500))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    branding: Mapped[OrganizationBrandingModel | None] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    services: Mapped[list[OrganizationServiceModel]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationBrandingModel(Base):
    __tablename__ = "organization_branding"

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    brand_name: Mapped[str] = mapped_column(String(200))
    logo_reference: Mapped[str | None] = mapped_column(String(500))
    primary_color: Mapped[str] = mapped_column(String(7), default="#2563EB")
    secondary_color: Mapped[str] = mapped_column(String(7), default="#0F172A")
    accent_color: Mapped[str] = mapped_column(String(7), default="#14B8A6")
    proposal_footer: Mapped[str | None] = mapped_column(Text)
    email_signature: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    organization: Mapped[OrganizationModel] = relationship(back_populates="branding")


class OrganizationServiceModel(Base):
    __tablename__ = "organization_services"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_services_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    short_description: Mapped[str | None] = mapped_column(String(500))
    full_description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    organization: Mapped[OrganizationModel] = relationship(back_populates="services")


class CompanyModel(Base):
    """Database representation of a company lead."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_companies_org_name"),
        UniqueConstraint("organization_id", "website", name="uq_companies_org_website"),
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
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
    ai_analyses: Mapped[list[DiscoveryAIAnalysisModel]] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )


class DiscoveryScanModel(Base):
    """A persisted snapshot of observable website discovery signals."""

    __tablename__ = "discovery_scans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
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
    ai_analyses: Mapped[list[DiscoveryAIAnalysisModel]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )


class DiscoveryAIAnalysisModel(Base):
    __tablename__ = "discovery_ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    discovery_scan_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_scans.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="Pending", index=True)
    review_status: Mapped[str] = mapped_column(
        String(20), default="Unreviewed", index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(30))
    schema_version: Mapped[str] = mapped_column(String(30))
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    executive_summary: Mapped[str | None] = mapped_column(Text)
    business_profile: Mapped[str | None] = mapped_column(Text)
    digital_strengths: Mapped[str] = mapped_column(Text, default="[]")
    improvement_areas: Mapped[str] = mapped_column(Text, default="[]")
    business_risks: Mapped[str] = mapped_column(Text, default="[]")
    quick_wins: Mapped[str] = mapped_column(Text, default="[]")
    strategic_opportunities: Mapped[str] = mapped_column(Text, default="[]")
    recommended_services: Mapped[str] = mapped_column(Text, default="[]")
    implementation_roadmap: Mapped[str] = mapped_column(Text, default="[]")
    discovery_questions: Mapped[str] = mapped_column(Text, default="[]")
    outreach_angles: Mapped[str] = mapped_column(Text, default="[]")
    confidence_notes: Mapped[str | None] = mapped_column(Text)
    evidence_references: Mapped[str] = mapped_column(Text, default="[]")
    input_snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    input_token_count: Mapped[int | None] = mapped_column(Integer)
    output_token_count: Mapped[int | None] = mapped_column(Integer)
    total_token_count: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    raw_response_metadata: Mapped[str] = mapped_column(Text, default="{}")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    scan: Mapped[DiscoveryScanModel] = relationship(back_populates="ai_analyses")
    company: Mapped[CompanyModel] = relationship(back_populates="ai_analyses")
