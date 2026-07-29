from unittest.mock import patch

import pytest
from sqlalchemy import create_mock_engine, text

from leadpilot.infrastructure.database.engine import create_database_engine
from leadpilot.infrastructure.database.session import create_session_factory


def test_database_connectivity_and_session_factory() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        assert session.scalar(text("SELECT 1")) == 1

    engine.dispose()


def test_sqlite_foreign_keys_are_enabled() -> None:
    engine = create_database_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1

    engine.dispose()


def test_postgresql_engine_uses_safe_pooling_without_sqlite_arguments() -> None:
    mock_engine = create_mock_engine(
        "postgresql+psycopg://user:password@example.test/postgres",
        lambda *_args, **_kwargs: None,
    )
    with patch(
        "leadpilot.infrastructure.database.engine.create_engine",
        return_value=mock_engine,
    ) as create:
        result = create_database_engine(
            "postgresql+psycopg://user:password@example.test/postgres"
        )
    assert result is mock_engine
    options = create.call_args.kwargs
    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == 5
    assert options["max_overflow"] == 5
    assert options["pool_recycle"] == 1800
    assert "connect_args" not in options


@pytest.mark.parametrize(
    "url",
    (
        "",
        "mysql+pymysql://user:password@example.test/database",
        "postgresql://user:password@example.test/postgres",
    ),
)
def test_invalid_database_configuration_fails_clearly(url: str) -> None:
    with pytest.raises(ValueError, match="LEADPILOT_DATABASE_URL|PostgreSQL URLs"):
        create_database_engine(url)
