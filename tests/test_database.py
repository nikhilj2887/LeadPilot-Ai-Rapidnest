from sqlalchemy import text

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
