# LeadPilot AI

LeadPilot AI is RapidNest's lead-intelligence application. Milestone 2 adds a complete company pipeline to the production-oriented foundation: persisted companies, application services, Streamlit CRUD workflows, and dashboard metrics.

## Milestone 2 features

- Create, browse, search, update, and delete prospect companies.
- Track a company's website, industry, location, size, pipeline status, source, and notes.
- Search and filter companies, review detail views, and browse results ten at a time.
- Monitor lead-stage counts, recent companies, and status distribution on the dashboard.
- Persist data in SQLite through SQLAlchemy 2.x and version the schema with Alembic.

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
python -m pytest
```

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

This milestone intentionally does not add contacts, authentication, scoring, proposals, external AI providers, or integrations.
