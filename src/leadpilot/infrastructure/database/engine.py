from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, NoSuchModuleError

POSTGRESQL_POOL_SIZE = 5
POSTGRESQL_MAX_OVERFLOW = 5
POSTGRESQL_POOL_RECYCLE_SECONDS = 1800


def _ensure_sqlite_directory(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        return
    if url.database == ":memory:" or url.database.startswith("file:"):
        return
    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: str) -> Engine:
    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        raise ValueError(
            "LEADPILOT_DATABASE_URL is not a valid SQLAlchemy URL."
        ) from exc
    backend = url.get_backend_name()
    if backend not in {"sqlite", "postgresql"}:
        raise ValueError(
            "LEADPILOT_DATABASE_URL must use SQLite or PostgreSQL with psycopg."
        )
    if backend == "postgresql" and url.drivername != "postgresql+psycopg":
        raise ValueError(
            "PostgreSQL URLs must use the postgresql+psycopg:// SQLAlchemy scheme."
        )

    _ensure_sqlite_directory(database_url)
    options: dict[str, object] = {"pool_pre_ping": True}
    if backend == "postgresql":
        options.update(
            pool_size=POSTGRESQL_POOL_SIZE,
            max_overflow=POSTGRESQL_MAX_OVERFLOW,
            pool_recycle=POSTGRESQL_POOL_RECYCLE_SECONDS,
        )
    try:
        engine = create_engine(database_url, **options)
    except (ImportError, NoSuchModuleError) as exc:
        raise RuntimeError(
            "The configured database driver is unavailable. "
            "Install project dependencies and verify LEADPILOT_DATABASE_URL."
        ) from exc

    if backend == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine
