from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, MetaData, Table, func, inspect, select, text

APPLICATION_TABLES = (
    "organizations",
    "organization_branding",
    "organization_services",
    "users",
    "organization_memberships",
    "companies",
    "discovery_scans",
    "discovery_ai_analyses",
    "proposals",
    "proposal_items",
    "proposal_sections",
    "proposal_versions",
    "proposal_activities",
    "audit_logs",
)


@dataclass(frozen=True, slots=True)
class TableMigrationResult:
    table: str
    source_count: int
    inserted_count: int
    skipped_count: int


def validate_migration_engines(source: Engine, target: Engine) -> None:
    if source.dialect.name != "sqlite":
        raise ValueError("Source database must be SQLite.")
    if target.dialect.name != "postgresql":
        raise ValueError("Target database must be PostgreSQL.")
    if source.url.render_as_string(hide_password=True) == target.url.render_as_string(
        hide_password=True
    ):
        raise ValueError("Source and target databases must be different.")


def migrate_application_data(
    source: Engine, target: Engine, *, dry_run: bool = True
) -> list[TableMigrationResult]:
    validate_migration_engines(source, target)
    source_tables = set(inspect(source).get_table_names())
    target_tables = set(inspect(target).get_table_names())
    missing_source = set(APPLICATION_TABLES) - source_tables
    missing_target = set(APPLICATION_TABLES) - target_tables
    if missing_source:
        raise ValueError(
            f"Source is missing application tables: {sorted(missing_source)}"
        )
    if missing_target:
        raise ValueError(
            "Target schema is incomplete. Run 'alembic upgrade head' first. "
            f"Missing: {sorted(missing_target)}"
        )

    source_metadata = MetaData()
    target_metadata = MetaData()
    results: list[TableMigrationResult] = []
    with source.connect() as source_connection, target.begin() as target_connection:
        for table_name in APPLICATION_TABLES:
            source_table = Table(
                table_name, source_metadata, autoload_with=source_connection
            )
            target_table = Table(
                table_name, target_metadata, autoload_with=target_connection
            )
            rows = [
                dict(row)
                for row in source_connection.execute(select(source_table)).mappings()
            ]
            inserted = 0
            skipped = 0
            primary_keys = [column.name for column in target_table.primary_key.columns]
            for row in rows:
                existing = False
                if primary_keys:
                    predicates = [
                        target_table.c[name] == row[name] for name in primary_keys
                    ]
                    existing = (
                        target_connection.execute(
                            select(target_table).where(*predicates).limit(1)
                        ).first()
                        is not None
                    )
                if existing:
                    skipped += 1
                elif not dry_run:
                    target_connection.execute(target_table.insert().values(**row))
                    inserted += 1
            results.append(
                TableMigrationResult(table_name, len(rows), inserted, skipped)
            )
        if not dry_run:
            _reset_postgresql_sequences(target_connection, target_metadata)
        if dry_run:
            target_connection.rollback()
    return results


def _reset_postgresql_sequences(connection: object, metadata: MetaData) -> None:
    for table_name in APPLICATION_TABLES:
        table = metadata.tables[table_name]
        if "id" not in table.c or not table.c.id.primary_key:
            continue
        maximum = connection.scalar(select(func.max(table.c.id)))  # type: ignore[attr-defined]
        if maximum is None:
            continue
        connection.execute(  # type: ignore[attr-defined]
            text(
                "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
                ":maximum, true)"
            ),
            {"table_name": table_name, "maximum": maximum},
        )
