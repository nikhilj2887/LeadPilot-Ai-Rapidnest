# LeadPilot AI

LeadPilot AI is RapidNest's lead-intelligence application. This Milestone 1 repository contains only the production-oriented application foundation: configuration, structured logging, SQLite persistence, Alembic migrations, a health check, and a Streamlit shell. Business entities and lead-scoring features are intentionally not implemented yet.

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

Milestone 1 includes an empty baseline migration. No company, contact, authentication, scoring, proposal, or other business tables exist yet.
