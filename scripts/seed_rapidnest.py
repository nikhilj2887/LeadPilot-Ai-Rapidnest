from __future__ import annotations

import argparse

from leadpilot.infrastructure.database.engine import create_database_engine
from leadpilot.infrastructure.database.seed import seed_rapidnest
from leadpilot.infrastructure.database.session import create_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed canonical RapidNest data.")
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    engine = create_database_engine(args.database_url)
    try:
        organization_id = seed_rapidnest(create_session_factory(engine))
    finally:
        engine.dispose()
    print(f"RapidNest seed verified (organization ID {organization_id}).")


if __name__ == "__main__":
    main()
