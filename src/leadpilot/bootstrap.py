from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from leadpilot.application.health import HealthCheckService
from leadpilot.config import Settings, get_settings
from leadpilot.infrastructure.database.engine import create_database_engine
from leadpilot.infrastructure.database.session import create_session_factory
from leadpilot.logging import configure_logging


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    health_check: HealthCheckService

    def dispose(self) -> None:
        self.engine.dispose()


def bootstrap(settings: Settings | None = None) -> Container:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.numeric_log_level)
    engine = create_database_engine(resolved_settings.database_url)
    return Container(
        settings=resolved_settings,
        engine=engine,
        session_factory=create_session_factory(engine),
        health_check=HealthCheckService(engine, resolved_settings.environment),
    )
