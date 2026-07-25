from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True, slots=True)
class HealthStatus:
    application_status: str
    database_connected: bool
    environment: str
    database_error: str | None = None

    @property
    def is_healthy(self) -> bool:
        return self.application_status == "running" and self.database_connected


class HealthCheckService:
    def __init__(self, engine: Engine, environment: str) -> None:
        self._engine = engine
        self._environment = environment

    def check(self) -> HealthStatus:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            return HealthStatus(
                application_status="degraded",
                database_connected=False,
                environment=self._environment,
                database_error=str(exc),
            )
        return HealthStatus(
            application_status="running",
            database_connected=True,
            environment=self._environment,
        )
