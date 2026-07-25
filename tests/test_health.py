from sqlalchemy import create_engine

from leadpilot.application.health import HealthCheckService


def test_health_check_reports_connected_database() -> None:
    engine = create_engine("sqlite:///:memory:")
    service = HealthCheckService(engine, "test")

    result = service.check()

    assert result.is_healthy
    assert result.application_status == "running"
    assert result.database_connected is True
    assert result.environment == "test"
    assert result.database_error is None
    engine.dispose()


def test_health_check_reports_database_as_unavailable() -> None:
    # Use a deterministic test double rather than relying on an external outage.
    class BrokenEngine:
        def connect(self) -> None:
            from sqlalchemy.exc import OperationalError

            raise OperationalError("SELECT 1", {}, Exception("offline"))

    service = HealthCheckService(BrokenEngine(), "test")  # type: ignore[arg-type]
    result = service.check()

    assert result.is_healthy is False
    assert result.application_status == "degraded"
    assert result.database_connected is False
    assert result.database_error is not None
