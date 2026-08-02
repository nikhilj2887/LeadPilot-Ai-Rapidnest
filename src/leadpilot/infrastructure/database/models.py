from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
    memberships: Mapped[list[OrganizationMembershipModel]] = relationship(
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
    detailed_description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(120))
    problems_solved: Mapped[str] = mapped_column(Text, default="[]")
    business_benefits: Mapped[str] = mapped_column(Text, default="[]")
    deliverables: Mapped[str] = mapped_column(Text, default="[]")
    target_industries: Mapped[str] = mapped_column(Text, default="[]")
    pricing_model: Mapped[str] = mapped_column(String(20), default="CUSTOM", index=True)
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    estimated_timeline: Mapped[str | None] = mapped_column(String(200))
    tags: Mapped[str] = mapped_column(Text, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    organization: Mapped[OrganizationModel] = relationship(back_populates="services")


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supabase_user_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    platform_role: Mapped[str | None] = mapped_column(String(30), index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    memberships: Mapped[list[OrganizationMembershipModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OrganizationMembershipModel(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_memberships_organization_user"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="INVITED", index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    organization: Mapped[OrganizationModel] = relationship(back_populates="memberships")
    user: Mapped[UserModel] = relationship(back_populates="memberships")


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


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


class ProposalModel(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "proposal_number", name="uq_proposals_org_number"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    discovery_scan_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_scans.id", ondelete="SET NULL")
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
    )
    proposal_number: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    currency: Mapped[str] = mapped_column(String(3))
    valid_until: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    client_requirements: Mapped[str | None] = mapped_column(Text)
    recommended_approach: Mapped[str | None] = mapped_column(Text)
    implementation_plan: Mapped[str | None] = mapped_column(Text)
    commercial_notes: Mapped[str | None] = mapped_column(Text)
    terms_and_conditions: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProposalItemModel(Base):
    __tablename__ = "proposal_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    service_catalog_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_services.id", ondelete="SET NULL")
    )
    item_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=0)
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    line_tax: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    delivery_timeline: Mapped[str | None] = mapped_column(String(200))
    selection_reason: Mapped[str | None] = mapped_column(Text)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProposalSectionModel(Base):
    __tablename__ = "proposal_sections"
    __table_args__ = (
        UniqueConstraint("proposal_id", "section_key", name="uq_proposal_sections_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    section_key: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer)
    content_source: Mapped[str] = mapped_column(String(30), default="EMPTY")
    last_ai_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="SET NULL")
    )
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProposalVersionModel(Base):
    __tablename__ = "proposal_versions"
    __table_args__ = (
        UniqueConstraint(
            "proposal_id", "version_number", name="uq_proposal_versions_number"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProposalActivityModel(Base):
    __tablename__ = "proposal_activities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    activity_type: Mapped[str] = mapped_column(String(30), index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AIProviderConfigModel(Base):
    __tablename__ = "ai_provider_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(30), index=True)
    model_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    temperature: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.1"))
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    request_timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    monthly_token_limit: Mapped[int | None] = mapped_column(Integer)
    monthly_cost_limit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    credentials_reference: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PromptTemplateModel(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "template_key",
            "version",
            name="uq_prompt_templates_org_key_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    template_key: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    system_template: Mapped[str] = mapped_column(Text)
    user_template: Mapped[str] = mapped_column(Text)
    response_schema_version: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AIRunModel(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_ai_runs_org_idempotency",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposals.id", ondelete="SET NULL"), index=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    discovery_scan_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_scans.id", ondelete="SET NULL")
    )
    run_type: Mapped[str] = mapped_column(String(40), index=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    model_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), index=True)
    prompt_template_key: Mapped[str | None] = mapped_column(String(100))
    prompt_template_version: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    input_hash: Mapped[str] = mapped_column(String(64))
    input_snapshot_json: Mapped[str] = mapped_column(Text)
    output_json: Mapped[str | None] = mapped_column(Text)
    raw_output_reference: Mapped[str | None] = mapped_column(String(500))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(500))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    finish_reason: Mapped[str | None] = mapped_column(String(100))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ProposalRecommendationModel(Base):
    __tablename__ = "proposal_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    service_catalog_id: Mapped[int] = mapped_column(
        ForeignKey("organization_services.id", ondelete="RESTRICT"), index=True
    )
    ai_run_id: Mapped[int] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), index=True)
    match_score: Mapped[int] = mapped_column(Integer)
    deterministic_score: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(10), index=True)
    recommendation_reason: Mapped[str] = mapped_column(Text)
    matched_findings_json: Mapped[str] = mapped_column(Text, default="[]")
    expected_benefits_json: Mapped[str] = mapped_column(Text, default="[]")
    suggested_scope: Mapped[str] = mapped_column(Text)
    suggested_timeline: Mapped[str | None] = mapped_column(String(200))
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    added_proposal_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposal_items.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProposalGenerationDraftModel(Base):
    __tablename__ = "proposal_generation_drafts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    ai_run_id: Mapped[int] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="RESTRICT"), index=True
    )
    generation_type: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    tone: Mapped[str] = mapped_column(String(20))
    instructions: Mapped[str | None] = mapped_column(Text)
    requested_section_keys_json: Mapped[str] = mapped_column(Text)
    generated_sections_json: Mapped[str] = mapped_column(Text)
    source_references_json: Mapped[str | None] = mapped_column(Text)
    warnings_json: Mapped[str | None] = mapped_column(Text)
    applied_section_keys_json: Mapped[str | None] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    applied_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProposalDocumentModel(Base):
    __tablename__ = "proposal_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    proposal_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposal_versions.id", ondelete="SET NULL"), index=True
    )
    document_type: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    storage_provider: Mapped[str] = mapped_column(String(30))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    file_name: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256_checksum: Mapped[str | None] = mapped_column(String(64))
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_snapshot_json: Mapped[str] = mapped_column(Text)
    branding_snapshot_json: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    generated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
    safe_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailProviderConfigModel(Base):
    __tablename__ = "email_provider_configs"
    __table_args__ = (
        CheckConstraint(
            "smtp_port IS NULL OR (smtp_port >= 1 AND smtp_port <= 65535)",
            name="ck_email_provider_configs_port",
        ),
        CheckConstraint(
            "NOT (smtp_use_tls AND smtp_use_ssl)",
            name="ck_email_provider_configs_transport",
        ),
        Index(
            "ix_email_provider_configs_resolution",
            "organization_id",
            "provider",
            "is_active",
            "is_default",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(30), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    from_address: Mapped[str] = mapped_column(String(320))
    from_name: Mapped[str] = mapped_column(String(200))
    reply_to_address: Mapped[str | None] = mapped_column(String(320))
    credentials_reference: Mapped[str | None] = mapped_column(String(300))
    smtp_host: Mapped[str | None] = mapped_column(String(255))
    smtp_port: Mapped[int | None] = mapped_column(Integer)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    smtp_use_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    request_timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProposalEmailDeliveryModel(Base):
    __tablename__ = "proposal_email_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_proposal_email_deliveries_idempotency",
        ),
        CheckConstraint(
            "attempt_count >= 0", name="ck_proposal_email_deliveries_attempt_count"
        ),
        Index(
            "ix_proposal_email_deliveries_history",
            "organization_id",
            "proposal_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    proposal_document_id: Mapped[int] = mapped_column(
        ForeignKey("proposal_documents.id", ondelete="RESTRICT"), index=True
    )
    provider_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_provider_configs.id", ondelete="SET NULL"), index=True
    )
    original_delivery_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposal_email_deliveries.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    from_address: Mapped[str] = mapped_column(String(320))
    from_name: Mapped[str] = mapped_column(String(200))
    reply_to_address: Mapped[str | None] = mapped_column(String(320))
    to_addresses_json: Mapped[str] = mapped_column(Text)
    cc_addresses_json: Mapped[str] = mapped_column(Text, default="[]")
    bcc_addresses_json: Mapped[str] = mapped_column(Text, default="[]")
    subject: Mapped[str] = mapped_column(String(300))
    html_body: Mapped[str] = mapped_column(Text)
    text_body: Mapped[str] = mapped_column(Text)
    attachment_file_name: Mapped[str] = mapped_column(String(200))
    attachment_sha256_checksum: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(30), index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(300))
    provider_response_json: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    safe_error_code: Mapped[str | None] = mapped_column(String(100))
    safe_error_message: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProposalPortalLinkModel(Base):
    __tablename__ = "proposal_portal_links"
    __table_args__ = (
        CheckConstraint("access_count >= 0", name="ck_portal_links_access_count"),
        CheckConstraint(
            "max_access_count IS NULL OR max_access_count > 0",
            name="ck_portal_links_max_access_count",
        ),
        Index(
            "ix_proposal_portal_links_history",
            "organization_id",
            "proposal_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    proposal_document_id: Mapped[int] = mapped_column(
        ForeignKey("proposal_documents.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_prefix: Mapped[str] = mapped_column(String(12))
    password_hash: Mapped[str | None] = mapped_column(String(500))
    password_required: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    max_access_count: Mapped[int | None] = mapped_column(Integer)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    allow_pdf_download: Mapped[bool] = mapped_column(Boolean, default=True)
    show_pricing: Mapped[bool] = mapped_column(Boolean, default=True)
    show_internal_branding_details: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProposalPortalAccessEventModel(Base):
    __tablename__ = "proposal_portal_access_events"
    __table_args__ = (
        Index(
            "ix_proposal_portal_access_events_history",
            "organization_id",
            "portal_link_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    portal_link_id: Mapped[int] = mapped_column(
        ForeignKey("proposal_portal_links.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    access_result: Mapped[str] = mapped_column(String(20), index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))
    session_hash: Mapped[str | None] = mapped_column(String(64))
    safe_metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ProposalAcceptanceModel(Base):
    __tablename__ = "proposal_acceptances"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_proposal_acceptances_status",
        ),
        CheckConstraint(
            "signature_type IS NULL OR signature_type IN ('TYPED', 'HANDWRITTEN')",
            name="ck_proposal_acceptances_signature_type",
        ),
        Index(
            "uq_proposal_acceptances_one_accepted",
            "proposal_id",
            unique=True,
            sqlite_where=text("status = 'ACCEPTED'"),
            postgresql_where=text("status = 'ACCEPTED'"),
        ),
        Index(
            "ix_proposal_acceptances_history",
            "organization_id",
            "proposal_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="RESTRICT"), index=True
    )
    proposal_portal_link_id: Mapped[int] = mapped_column(
        ForeignKey("proposal_portal_links.id", ondelete="RESTRICT"), index=True
    )
    proposal_document_id: Mapped[int] = mapped_column(
        ForeignKey("proposal_documents.id", ondelete="RESTRICT"), index=True
    )
    signed_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposal_documents.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    accepted_by_name: Mapped[str | None] = mapped_column(String(200))
    accepted_by_email: Mapped[str | None] = mapped_column(String(320))
    accepted_by_company: Mapped[str | None] = mapped_column(String(200))
    accepted_by_title: Mapped[str | None] = mapped_column(String(200))
    signature_type: Mapped[str | None] = mapped_column(String(20))
    typed_signature: Mapped[str | None] = mapped_column(String(200))
    signature_image_path: Mapped[str | None] = mapped_column(String(500))
    comments: Mapped[str | None] = mapped_column(Text)
    client_ip_hash: Mapped[str | None] = mapped_column(String(64))
    client_user_agent_hash: Mapped[str | None] = mapped_column(String(64))
    client_session_hash: Mapped[str | None] = mapped_column(String(64))
    evidence_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ProposalEngagementEventModel(Base):
    __tablename__ = "proposal_engagement_events"
    __table_args__ = (
        CheckConstraint(
            "page_number IS NULL OR page_number > 0", name="ck_engagement_page_number"
        ),
        CheckConstraint(
            "duration_ms IS NULL OR (duration_ms >= 0 AND duration_ms <= 86400000)",
            name="ck_engagement_duration",
        ),
        Index(
            "ix_proposal_engagement_timeline",
            "organization_id",
            "proposal_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    portal_link_id: Mapped[int] = mapped_column(
        ForeignKey("proposal_portal_links.id", ondelete="CASCADE"), index=True
    )
    proposal_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposal_documents.id", ondelete="SET NULL")
    )
    visitor_id: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    page_number: Mapped[int | None]
    section_key: Mapped[str | None] = mapped_column(String(100))
    duration_ms: Mapped[int | None]
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ContactModel(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("company_id", "email", name="uq_contacts_company_email"),
        Index("ix_contacts_org_company", "organization_id", "company_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    job_title: Mapped[str | None] = mapped_column(String(150))
    department: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    mobile: Mapped[str | None] = mapped_column(String(50))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    preferred_contact_method: Mapped[str] = mapped_column(String(20), default="NONE")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PipelineStageModel(Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_pipeline_stage_org_code"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    stage_type: Mapped[str] = mapped_column(String(20), default="OPEN")
    probability_percentage: Mapped[int] = mapped_column(Integer)
    display_order: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LeadModel(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("organization_id", "lead_number", name="uq_leads_org_number"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    lead_number: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="NEW", index=True)
    qualification_status: Mapped[str] = mapped_column(
        String(30), default="UNASSESSED", index=True
    )
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM", index=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    industry: Mapped[str | None] = mapped_column(String(150))
    country: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown_json: Mapped[str] = mapped_column(Text, default="{}")
    qualification_notes: Mapped[str | None] = mapped_column(Text)
    disqualification_reason: Mapped[str | None] = mapped_column(Text)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    converted_opportunity_id: Mapped[int | None] = mapped_column(Integer)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OpportunityModel(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "opportunity_number", name="uq_opportunities_org_number"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    primary_contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    source_lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )
    stage_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_stages.id", ondelete="RESTRICT"), index=True
    )
    opportunity_number: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    probability_percentage: Mapped[int] = mapped_column(Integer)
    weighted_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    expected_close_date: Mapped[date | None] = mapped_column(Date, index=True)
    actual_close_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    win_reason: Mapped[str | None] = mapped_column(Text)
    loss_reason: Mapped[str | None] = mapped_column(Text)
    competitor: Mapped[str | None] = mapped_column(String(200))
    next_step: Mapped[str | None] = mapped_column(Text)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CrmActivityModel(Base):
    __tablename__ = "crm_activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    activity_type: Mapped[str] = mapped_column(String(30), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PLANNED", index=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE")
    )
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    performed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    duration_minutes: Mapped[int | None]
    outcome: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CrmTaskModel(Base):
    __tablename__ = "crm_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE")
    )
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE")
    )
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CrmNoteModel(Base):
    __tablename__ = "crm_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE")
    )
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE")
    )
    content: Mapped[str] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CrmStageHistoryModel(Base):
    __tablename__ = "crm_stage_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    from_stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("pipeline_stages.id", ondelete="RESTRICT")
    )
    to_stage_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_stages.id", ondelete="RESTRICT")
    )
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    change_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CrmAssignmentHistoryModel(Base):
    __tablename__ = "crm_assignment_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int] = mapped_column(Integer)
    from_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assignment_method: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
