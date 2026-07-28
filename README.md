# LeadPilot AI

LeadPilot AI is RapidNest's lead-intelligence application. Milestone 4 adds
deterministic public-website discovery and explainable lead scoring to the
persisted company pipeline.

## Milestone 4 website discovery

- Run a synchronous scan for an existing company, retain scan history, and view
  the latest result on Company detail, Discovery, and Dashboard screens.
- Inspect the homepage, `robots.txt`, `sitemap.xml`, and up to eight relevant
  same-domain pages without JavaScript execution, form submission, or login.
- Extract metadata, business pages, contact details, social links, engagement
  signals, and evidence-backed technology indicators.
- Produce Website Health, Digital Maturity, AI Readiness, Automation Potential,
  and Lead Priority scores with ratings, factors, and concise explanations.
- Generate evidence-linked findings and RapidNest opportunities using rules.

## Milestone 4.1 UX polish

- Uses a responsive application canvas up to 1560px with readable typography,
  equal-height KPI cards, balanced dashboard panels, and tablet-safe spacing.
- Moves Discovery Intelligence higher on the Dashboard and adds completed scans,
  high-priority leads, average automation potential, average AI readiness, and
  recently scanned companies.
- Presents website health, business signals, technologies, findings, contact
  details, social links, and scan metadata as business-readable tables and cards
  instead of raw JSON-like output.
- Gives RapidNest Opportunities prominent evidence, outcomes, and priorities,
  clearly framed as assessment opportunities rather than confirmed requirements.
- Isolates page and dashboard-section failures so optional reporting errors no
  longer appear as false application startup failures.

Scanning, SSRF protection, persistence, and all five scoring calculations remain
unchanged and deterministic. No AI provider is used.

Discovery uses no OpenAI, Anthropic, Gemini, or other AI provider. All scores
are deterministic, website-observable indicators and must not be interpreted as
knowledge of a company's internal systems. Proposals remains a placeholder.

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
layer has no Streamlit dependency. Discovery orchestration, HTTP fetching, URL
security, HTML analysis, technology detection, scoring, persistence, and UI
rendering are separate modules. Database changes are managed only with Alembic.

## Configuration

Configuration is loaded from environment variables and an optional `.env` file. See `.env.example` for all current settings.

| Variable | Default | Description |
| --- | --- | --- |
| `LEADPILOT_ENV` | `development` | Runtime environment name |
| `LEADPILOT_LOG_LEVEL` | `INFO` | Structured logging threshold |
| `LEADPILOT_DATABASE_URL` | `sqlite:///./data/leadpilot.db` | SQLAlchemy database URL |
| `LEADPILOT_APP_NAME` | `LeadPilot AI` | Application display name |
| `LEADPILOT_DISCOVERY_CONNECT_TIMEOUT` | `5` | Connect timeout in seconds |
| `LEADPILOT_DISCOVERY_READ_TIMEOUT` | `10` | Read timeout in seconds |
| `LEADPILOT_DISCOVERY_MAX_PAGES` | `9` | Maximum pages including homepage |
| `LEADPILOT_DISCOVERY_MAX_RESPONSE_BYTES` | `2000000` | Per-response size limit |
| `LEADPILOT_DISCOVERY_USER_AGENT` | `LeadPilot/0.1 Website Discovery` | Scanner identity |
| `LEADPILOT_DISCOVERY_RETRY_COUNT` | `1` | Safe transient retry count |
| `LEADPILOT_DISCOVERY_SLOW_RESPONSE_MS` | `3000` | Slow response scoring threshold |

## Database migrations

Apply all migrations:

```bash
python -m alembic upgrade head
```

Create a future migration after adding SQLAlchemy models:

```bash
python -m alembic revision --autogenerate -m "describe the schema change"
```

The discovery migration adds company-owned scan records. The foreign key uses
`ON DELETE CASCADE`, with SQLite foreign keys explicitly enabled, so deleting a
company deliberately deletes its scan history.

## Discovery security and limitations

Discovery accepts only HTTP(S), resolves the hostname before each request, and
rejects loopback, private, link-local, reserved, multicast, and other non-global
addresses. Every redirect target is independently validated. TLS verification
remains enabled, response bodies are size-limited, HTML content is required for
pages, crawling stays on the same hostname, scripts are never executed, and raw
HTML, cookies, authorization headers, tokens, and stack traces are not stored.

Pre-request DNS checks substantially reduce SSRF risk but cannot eliminate DNS
rebinding between validation and connection because the HTTP transport performs
its own DNS lookup. Production deployments should also enforce outbound network
controls or use a resolver-pinned transport. The scanner does not execute
JavaScript, so client-rendered signals may be absent. Technology detection is
indicator-based and absence of a visible tool does not prove it is absent
internally.

## Company data

Companies require a unique name and one of these pipeline statuses: `New`, `Researching`, `Qualified`, `Contacted`, `Proposal`, `Won`, or `Lost`. Supported company sizes are `Solo`, `2-10`, `11-50`, `51-200`, `201-500`, `501-1000`, and `1000+`.

Websites may be entered with or without a scheme; bare domains such as `example.com` are normalized to `https://example.com`. Industry, country, city, company size, source, and notes are optional. Company names are treated as case-insensitively unique by the application.

Discovery runs synchronously in Milestone 4; there are no workers, queues,
schedules, search-engine scraping, proposal generation, or external AI providers.
