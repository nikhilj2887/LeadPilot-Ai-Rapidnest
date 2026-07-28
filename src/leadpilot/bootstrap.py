from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.ai_provider import AIProviderError, DisabledAIProvider
from leadpilot.application.companies import CompanyService
from leadpilot.application.discovery import DiscoveryService
from leadpilot.application.discovery_ai import DiscoveryAIService
from leadpilot.application.health import HealthCheckService
from leadpilot.application.organizations import OrganizationContext
from leadpilot.config import Settings, get_settings
from leadpilot.infrastructure.ai_providers import create_ai_provider
from leadpilot.infrastructure.database.ai_analysis_repository import (
    AIAnalysisRepository,
)
from leadpilot.infrastructure.database.company_repository import CompanyRepository
from leadpilot.infrastructure.database.discovery_repository import DiscoveryRepository
from leadpilot.infrastructure.database.engine import create_database_engine
from leadpilot.infrastructure.database.organization_repository import (
    OrganizationRepository,
)
from leadpilot.infrastructure.database.session import create_session_factory
from leadpilot.infrastructure.discovery_client import WebsiteClient
from leadpilot.infrastructure.discovery_scanner import WebsiteScanner
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
    discovery: DiscoveryService
    discovery_ai: DiscoveryAIService

    def dispose(self) -> None:
        self.engine.dispose()


def bootstrap(
    settings: Settings | None = None, organization_id: int | None = None
) -> Container:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.numeric_log_level)
    engine = create_database_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)
    organization_repository = OrganizationRepository(session_factory)
    organization_context = OrganizationContext.resolve(
        organization_repository, organization_id
    )
    selected_id = organization_context.organization_id
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
    )
    try:
        ai_provider = create_ai_provider(resolved_settings)
    except AIProviderError:
        ai_provider = DisabledAIProvider()
    return Container(
        settings=resolved_settings,
        engine=engine,
        session_factory=session_factory,
        health_check=HealthCheckService(engine, resolved_settings.environment),
        organization_context=organization_context,
        organizations=organization_repository,
        companies=CompanyService(company_repository),
        discovery=discovery_service,
        discovery_ai=DiscoveryAIService(
            AIAnalysisRepository(session_factory, selected_id),
            CompanyService(company_repository),
            discovery_service,
            ai_provider,
            resolved_settings,
            organization_repository,
            selected_id,
        ),
    )
