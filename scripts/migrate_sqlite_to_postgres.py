from __future__ import annotations

import argparse

from leadpilot.infrastructure.database.data_migration import migrate_application_data
from leadpilot.infrastructure.database.engine import create_database_engine


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Copy LeadPilot-owned application data from SQLite to PostgreSQL."
    )
    command.add_argument("--source-url", required=True)
    command.add_argument("--target-url", required=True)
    command.add_argument(
        "--execute",
        action="store_true",
        help="Commit inserts. Without this flag the utility performs a dry run.",
    )
    return command


def main() -> None:
    args = parser().parse_args()
    source = create_database_engine(args.source_url)
    target = create_database_engine(args.target_url)
    try:
        results = migrate_application_data(source, target, dry_run=not args.execute)
    finally:
        source.dispose()
        target.dispose()
    mode = "MIGRATION COMPLETE" if args.execute else "DRY RUN — NO WRITES"
    print(mode)
    for result in results:
        print(
            f"{result.table}: source={result.source_count}, "
            f"inserted={result.inserted_count}, skipped={result.skipped_count}"
        )


if __name__ == "__main__":
    main()
