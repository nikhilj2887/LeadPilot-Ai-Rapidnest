# LeadPilot AI

LeadPilot AI is RapidNest's lead-intelligence application. Milestone 3 adds a
polished, responsive B2B SaaS interface to the persisted company pipeline while
keeping the modular-monolith architecture and existing business rules intact.

## Milestone 3 UI features

- A single branded application shell with responsive navigation, dark-mode-aware
  styling, and discreet environment and database health.
- A dashboard with five pipeline KPIs, all seven company statuses, recent
  companies, quick actions, and a useful zero-data experience.
- A professional Companies workspace with search, status/industry/country
  filters, five sort options, result counts, and ten-record pagination.
- Guided add and edit forms, a complete company profile, friendly validation
  messages, and explicit confirmation before deletion.
- Reusable page headers, KPI cards, badges, empty states, alerts, form sections,
  confirmation panels, and pagination behavior.
- Health-oriented Settings cards and polished previews for future Discovery and
  Proposals capabilities.

Discovery and Proposals are deliberately non-functional placeholders in this
milestone. They do not make external calls, run AI behavior, generate proposals,
or export files.

## Prerequisites (macOS)

- macOS with [Homebrew](https://brew.sh/) installed
- Python 3.12 or newer
- Git

## Exact setup commands (macOS)

Run the following commands from Terminal:

```bash
brew install python@3.12
git clone <repository-url> LeadPilot-Ai-Rapidnest
cd LeadPilot-Ai-Rapidnest
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m alembic upgrade head
```

Replace `<repository-url>` with the Git URL supplied by RapidNest.

## Run the application

From the repository root, with the virtual environment activated:

```bash
python -m streamlit run src/leadpilot/presentation/streamlit/app.py
```

Streamlit prints the local URL (normally `http://localhost:8501`) in the terminal.

## Run tests

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

## Architecture boundaries

Presentation modules call application services only. SQLAlchemy models,
sessions, and queries remain inside `infrastructure/database`; the application
layer has no Streamlit dependency. Styling and reusable UI helpers are separate
from company business logic, and database changes continue to be managed only
through Alembic. Milestone 3 adds no schema, business entities, authentication,
external APIs, AI providers, workers, contacts, or proposal functionality.

## Configuration

Configuration is loaded from environment variables and an optional `.env` file. See `.env.example` for all current settings.

| Variable | Default | Description |
| --- | --- | --- |
| `LEADPILOT_ENV` | `development` | Runtime environment name |
| `LEADPILOT_LOG_LEVEL` | `INFO` | Structured logging threshold |
| `LEADPILOT_DATABASE_URL` | `sqlite:///./data/leadpilot.db` | SQLAlchemy database URL |
| `LEADPILOT_APP_NAME` | `LeadPilot AI` | Application display name |

## Database migrations

Apply all migrations:

```bash
python -m alembic upgrade head
```

Create a future migration after adding SQLAlchemy models:

```bash
python -m alembic revision --autogenerate -m "describe the schema change"
```

The migration history contains the Milestone 1 baseline and the Milestone 2 `companies` table. Apply migrations before starting the application after every pull.

## Company data

Companies require a unique name and one of these pipeline statuses: `New`, `Researching`, `Qualified`, `Contacted`, `Proposal`, `Won`, or `Lost`. Supported company sizes are `Solo`, `2-10`, `11-50`, `51-200`, `201-500`, `501-1000`, and `1000+`.

Websites may be entered with or without a scheme; bare domains such as `example.com` are normalized to `https://example.com`. Industry, country, city, company size, source, and notes are optional. Company names are treated as case-insensitively unique by the application.

This milestone intentionally does not add contacts, authentication, scoring,
proposal generation, external AI providers, or integrations.
