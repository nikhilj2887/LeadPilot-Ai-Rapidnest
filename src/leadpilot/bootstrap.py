from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.ai_foundation import (
    AIOrchestrationService,
    AIProviderName,
)
from leadpilot.application.ai_foundation import (
    FakeAIProvider as FoundationFakeAIProvider,
)
from leadpilot.application.ai_provider import AIProviderError, DisabledAIProvider
from leadpilot.application.auth import (
    ROLE_LEVEL,
    AuthenticationService,
    AuthorizationError,
    OrganizationRole,
)
from leadpilot.application.companies import CompanyService
from leadpilot.application.discovery import DiscoveryService
from leadpilot.application.discovery_ai import DiscoveryAIService
from leadpilot.application.health import HealthCheckService
from leadpilot.application.offering_recommendations import OfferingRecommendationService
from leadpilot.application.organizations import OrganizationContext, OrganizationSummary
from leadpilot.application.prompt_templates import PromptTemplateService
from leadpilot.application.proposal_context_builder import ProposalContextBuilder
from leadpilot.application.proposal_email import (
    EmailProviderName,
    ProposalEmailService,
    ProposalEmailTemplateBuilder,
)
from leadpilot.application.proposal_generation import ProposalGenerationService
from leadpilot.application.proposal_pdf import ProposalPdfService
from leadpilot.application.proposal_pdf_snapshot import ProposalPdfSnapshotBuilder
from leadpilot.application.proposals import ProposalService
from leadpilot.application.service_catalog import ServiceCatalogService
from leadpilot.config import Settings, get_settings
from leadpilot.infrastructure.ai_providers import create_ai_provider
from leadpilot.infrastructure.database.ai_analysis_repository import (
    AIAnalysisRepository,
)
from leadpilot.infrastructure.database.ai_foundation_repository import (
    AIFoundationRepository,
)
from leadpilot.infrastructure.database.company_repository import CompanyRepository
from leadpilot.infrastructure.database.discovery_repository import DiscoveryRepository
from leadpilot.infrastructure.database.email_provider_config_repository import (
    EmailProviderConfigRepository,
)
from leadpilot.infrastructure.database.engine import create_database_engine
from leadpilot.infrastructure.database.identity_repository import IdentityRepository
from leadpilot.infrastructure.database.offering_recommendation_repository import (
    OfferingRecommendationRepository,
)
from leadpilot.infrastructure.database.organization_repository import (
    OrganizationRepository,
)
from leadpilot.infrastructure.database.prompt_template_repository import (
    SqlAlchemyPromptTemplateRepository,
)
from leadpilot.infrastructure.database.proposal_document_repository import (
    ProposalDocumentRepository,
)
from leadpilot.infrastructure.database.proposal_email_repository import (
    ProposalEmailRepository,
)
from leadpilot.infrastructure.database.proposal_generation_repository import (
    ProposalGenerationRepository,
)
from leadpilot.infrastructure.database.proposal_repository import (
    SqlAlchemyProposalRepository,
)
from leadpilot.infrastructure.database.service_catalog_repository import (
    ServiceCatalogRepository,
)
from leadpilot.infrastructure.database.session import create_session_factory
from leadpilot.infrastructure.discovery_client import WebsiteClient
from leadpilot.infrastructure.discovery_scanner import WebsiteScanner
from leadpilot.infrastructure.email_providers import (
    FakeEmailProvider,
    SMTPEmailProvider,
)
from leadpilot.infrastructure.gemini_provider import GeminiAIProvider
from leadpilot.infrastructure.pdf.reportlab_proposal_renderer import (
    ReportLabProposalPdfRenderer,
)
from leadpilot.infrastructure.storage.local_document_storage import LocalDocumentStorage
from leadpilot.infrastructure.supabase_auth import SupabaseAuthProvider
from leadpilot.logging import configure_logging


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    health_check: HealthCheckService
    organization_context: OrganizationContext
    organizations: OrganizationRepository
    companies: CompanyService
    service_catalog: ServiceCatalogService
    proposals: ProposalService
    discovery: DiscoveryService
    discovery_ai: DiscoveryAIService
    ai_orchestration: AIOrchestrationService
    ai_foundation_repository: AIFoundationRepository
    prompt_templates: PromptTemplateService
    offering_recommendations: OfferingRecommendationService
    proposal_generation: ProposalGenerationService
    proposal_pdf: ProposalPdfService
    proposal_email: ProposalEmailService
    identities: IdentityRepository

    def dispose(self) -> None:
        self.engine.dispose()


def bootstrap(
    settings: Settings | None = None,
    organization_id: int | None = None,
    user_id: int | None = None,
    organization_role: OrganizationRole | None = None,
) -> Container:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.numeric_log_level)
    engine = create_database_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)
    identity_repository = IdentityRepository(session_factory)
    organization_audit = lambda action, entity, entity_id: (
        identity_repository.log(
            action,
            entity,
            organization_id=int(entity_id),
            user_id=user_id,
            entity_id=entity_id,
        )
        if user_id is not None
        else None
    )
    organization_repository = OrganizationRepository(
        session_factory, organization_audit
    )
    organization_context = OrganizationContext.resolve(
        organization_repository, organization_id
    )
    selected_id = organization_context.organization_id
    audit = lambda action, entity, entity_id: (
        identity_repository.log(
            action,
            entity,
            organization_id=selected_id,
            user_id=user_id,
            entity_id=entity_id,
        )
        if user_id is not None
        else None
    )

    def require(minimum: OrganizationRole) -> None:
        if (
            organization_role is not None
            and ROLE_LEVEL[organization_role] < ROLE_LEVEL[minimum]
        ):
            raise AuthorizationError(f"{minimum.value} access or higher is required.")

    company_authorize = lambda: require(OrganizationRole.MANAGER)
    intelligence_authorize = lambda: require(OrganizationRole.ANALYST)
    company_repository = CompanyRepository(session_factory, selected_id)
    client = WebsiteClient(
        connect_timeout=resolved_settings.discovery_connect_timeout,
        read_timeout=resolved_settings.discovery_read_timeout,
        max_response_bytes=resolved_settings.discovery_max_response_bytes,
        user_agent=resolved_settings.discovery_user_agent,
        retry_count=resolved_settings.discovery_retry_count,
    )
    discovery_service = DiscoveryService(
        DiscoveryRepository(session_factory, selected_id),
        company_repository,
        WebsiteScanner(
            client,
            max_pages=resolved_settings.discovery_max_pages,
            slow_ms=resolved_settings.discovery_slow_response_ms,
        ),
        audit,
        intelligence_authorize,
    )
    try:
        ai_provider = create_ai_provider(resolved_settings)
    except AIProviderError:
        ai_provider = DisabledAIProvider()
    ai_foundation_repository = AIFoundationRepository(session_factory, selected_id)
    proposal_service = ProposalService(
        SqlAlchemyProposalRepository(session_factory, selected_id),
        user_id=user_id,
        authorize_write=company_authorize,
        audit=audit,
    )
    catalog_service = ServiceCatalogService(
        ServiceCatalogRepository(session_factory, selected_id),
        authorize_write=company_authorize,
        audit=audit,
    )
    ai_orchestration = AIOrchestrationService(
        ai_foundation_repository,
        {
            AIProviderName.GEMINI: GeminiAIProvider(),
            AIProviderName.FAKE: FoundationFakeAIProvider(),
        },
        audit=audit,
    )
    company_service = CompanyService(company_repository, audit, company_authorize)
    recommendation_service = OfferingRecommendationService(
        OfferingRecommendationRepository(session_factory, selected_id),
        ai_orchestration,
        proposal_service,
        company_service,
        discovery_service,
        catalog_service,
        selected_id,
        user_id,
        intelligence_authorize,
        audit,
    )
    proposal_pdf_service = ProposalPdfService(
        ProposalDocumentRepository(session_factory, selected_id),
        ProposalPdfSnapshotBuilder(
            proposal_service,
            company_service,
            organization_context,
            organization_repository,
            user_id,
        ),
        ReportLabProposalPdfRenderer(),
        LocalDocumentStorage(resolved_settings.document_storage_path),
        selected_id,
        user_id,
        company_authorize,
        audit,
        resolved_settings.pdf_max_file_size_mb,
    )
    email_configuration = EmailProviderConfigRepository(
        session_factory, selected_id, resolved_settings
    ).resolve()
    email_provider = None
    if email_configuration:
        if email_configuration.provider == EmailProviderName.SMTP:
            email_provider = SMTPEmailProvider(email_configuration)
        elif email_configuration.provider == EmailProviderName.FAKE:
            email_provider = FakeEmailProvider()
    branding = organization_repository.get_branding(selected_id)
    return Container(
        settings=resolved_settings,
        engine=engine,
        session_factory=session_factory,
        health_check=HealthCheckService(engine, resolved_settings.environment),
        organization_context=organization_context,
        organizations=organization_repository,
        companies=company_service,
        service_catalog=catalog_service,
        proposals=proposal_service,
        discovery=discovery_service,
        discovery_ai=DiscoveryAIService(
            AIAnalysisRepository(session_factory, selected_id),
            CompanyService(company_repository, audit, company_authorize),
            discovery_service,
            ai_provider,
            resolved_settings,
            organization_repository,
            selected_id,
            intelligence_authorize,
        ),
        ai_orchestration=ai_orchestration,
        ai_foundation_repository=ai_foundation_repository,
        prompt_templates=PromptTemplateService(
            SqlAlchemyPromptTemplateRepository(session_factory, selected_id)
        ),
        offering_recommendations=recommendation_service,
        proposal_generation=ProposalGenerationService(
            ProposalGenerationRepository(session_factory, selected_id),
            ai_orchestration,
            ProposalContextBuilder(
                proposal_service,
                company_service,
                discovery_service,
                recommendation_service,
                organization_context.organization,
            ),
            proposal_service,
            selected_id,
            user_id,
            intelligence_authorize,
            audit,
        ),
        proposal_pdf=proposal_pdf_service,
        proposal_email=ProposalEmailService(
            ProposalEmailRepository(session_factory, selected_id),
            proposal_service,
            proposal_pdf_service,
            email_provider,
            email_configuration,
            ProposalEmailTemplateBuilder(),
            organization_context.organization,
            branding,
            user_id,
            company_authorize,
            audit,
            resolved_settings.email_max_attachment_mb,
        ),
        identities=identity_repository,
    )


def bootstrap_auth(settings: Settings | None = None) -> AuthenticationService:
    resolved_settings = settings or get_settings()
    if not resolved_settings.auth_enabled:
        raise RuntimeError("Authentication is not configured.")
    engine = create_database_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)
    provider = SupabaseAuthProvider(
        resolved_settings.supabase_url or "",
        resolved_settings.supabase_anon_key or "",
        service_role_key=resolved_settings.supabase_service_role_key,
    )
    return AuthenticationService(provider, IdentityRepository(session_factory))


def list_active_organizations(
    settings: Settings | None = None,
) -> list[OrganizationSummary]:
    resolved_settings = settings or get_settings()
    engine = create_database_engine(resolved_settings.database_url)
    try:
        repository = OrganizationRepository(create_session_factory(engine))
        return repository.list_active()
    finally:
        engine.dispose()
