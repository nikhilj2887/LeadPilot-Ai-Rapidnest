# LeadPilot AI Repository Guidance

## Architecture

- Preserve the modular-monolith boundaries under `src/leadpilot`.
- Presentation code may depend on application services; application code must not depend on Streamlit.
- Keep SQLAlchemy details inside `infrastructure/database`.
- Do not add business entities, authentication, external AI providers, multi-tenancy, workers, webhooks, or integrations until their milestone is approved.
- Keep imports free of side effects: opening database connections and rendering UI must happen through explicit entry points.

## Development

- Support Python 3.12 and newer.
- Use SQLAlchemy 2.x APIs and typed Python interfaces.
- Add or update tests with every behavior change.
- Run `python -m pytest` before submitting changes.
- Manage database changes exclusively with Alembic migrations.
