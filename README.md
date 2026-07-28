# LeadPilot AI

![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.x-FF4B4B?logo=streamlit&logoColor=white)
![SQLAlchemy 2](https://img.shields.io/badge/SQLAlchemy-2.x-D71F00)
![Tests](https://img.shields.io/badge/pytest-85%20passing-0A9EDC?logo=pytest&logoColor=white)
![Code style: Ruff](https://img.shields.io/badge/code%20style-Ruff-D7FF64?logo=ruff&logoColor=black)
![Status](https://img.shields.io/badge/status-active%20development-2563EB)

LeadPilot AI is an AI-powered Lead Intelligence Platform built by RapidNest.

LeadPilot AI helps software companies and consulting firms discover qualified
prospects, analyse websites, identify digital gaps, uncover AI and automation
opportunities, and prepare discovery insights for sales conversations.

## Product Overview

LeadPilot AI is designed to help consulting and software teams:

- Manage target companies and their lead status.
- Analyse public websites and selected internal pages.
- Detect technologies, business signals, contact channels, and social presence.
- Assess website health, digital maturity, and AI readiness.
- Identify automation opportunities and prioritise leads.
- Prepare structured discovery insights for future AI-assisted workflows and
  proposals.

Discovery scoring remains deterministic. Scores and recommendations
use only publicly observable website evidence; they do not confirm or infer a
company's internal systems as facts. Milestone 5 adds an optional, separately
stored AI interpretation layer; it never changes deterministic scores.

### AI Discovery Intelligence

Milestone 5 turns a completed scan's normalized structured evidence into a
schema-validated, versioned business draft. A provider-neutral application
contract isolates OpenAI SDK details in an infrastructure adapter and supports a
deterministic fake provider for tests and explicit local demonstration.

The AI receives no raw HTML and performs no independent browsing. Stable evidence
identifiers ground important claims, unknown references are rejected, website
content is treated as untrusted data, and the versioned system prompt explicitly
rejects prompt injection and unsupported facts. Every result is marked
**AI-generated draft — review before client use**, retains history, supports
current/stale detection, and can be marked Unreviewed, Reviewed, or Needs Changes.

## Current Features

### Company Management

- Add, edit, view, and delete companies.
- Search and filter by lead attributes.
- Sort and paginate the company directory.
- Track companies across defined lead statuses.
- Review complete company detail pages and discovery history.

### Website Discovery Engine

- Secure, synchronous website scanning.
- Homepage, `robots.txt`, `sitemap.xml`, and selected same-domain page analysis.
- Evidence-backed technology detection.
- Business, engagement, social, and contact signal detection.
- Stored scan history and rescanning.
- Friendly, safely persisted failure handling.

### Lead Intelligence Scoring

LeadPilot AI calculates five explainable scores from 0 to 100:

| Score | Purpose |
| --- | --- |
| Website Health Score | Evaluates public technical health, metadata, HTTPS, response status, and discoverability signals. |
| Digital Maturity Score | Evaluates the visible platform, analytics, business content, engagement, and social footprint. |
| AI Readiness Score | Estimates readiness using observable digital touchpoints and workflows without claiming internal knowledge. |
| Automation Potential Score | Highlights visible opportunities where RapidNest may be able to improve customer and operational workflows. |
| Lead Priority Score | Combines opportunity, readiness, maturity gaps, health gaps, engagement, and contactability for qualification. |

Every score includes a numeric value, rating, explanation, positive factors, and
negative factors. Findings and recommendations retain the supporting website
evidence.

### Discovery Reports

Each completed scan provides:

- Executive Overview
- Website Health
- Technology Stack
- Business Signals
- Customer Engagement
- Social Presence
- Findings
- RapidNest Opportunities
- Contact Information
- Scan Metadata

### Dashboard

- Pipeline KPIs and company status overview.
- Recent companies and prominent company actions.
- Completed scan and high-priority lead metrics.
- Average automation potential and AI readiness.
- Recently scanned companies.
- Responsive quick actions.

## RapidNest Opportunity Areas

Rule-based recommendations may identify evidence-supported assessment
opportunities related to:

- AI Chatbots
- WhatsApp Automation
- CRM Integration
- Business Process Automation
- Appointment Automation
- Website Modernization
- Mobile Applications
- Cloud and Digital Transformation

These recommendations are assessment opportunities derived from visible website
signals. They are not confirmed internal requirements.

## Architecture

LeadPilot AI is a typed Python modular monolith using:

- Python 3.12+
- Streamlit
- SQLAlchemy 2.x
- Alembic
- SQLite
- Repository Pattern
- Service Layer
- pytest
- Ruff

The application separates presentation, application services, repositories,
persistence, website fetching, SSRF validation, HTML analysis, technology
detection, deterministic scoring, and discovery orchestration. Streamlit views
call services and do not query SQLAlchemy directly.

The boundaries support a future evolution toward FastAPI, React, PostgreSQL,
background workers, and multi-user SaaS deployment. Those capabilities are not
implemented yet.

## Security

The Discovery engine implements:

- HTTP and HTTPS schemes only.
- SSRF protection and public-IP validation.
- Localhost, loopback, private, link-local, reserved, and metadata endpoint
  rejection.
- Validation of every redirect target.
- TLS certificate verification.
- Response-size and content-type limits.
- Same-domain crawl restrictions and a maximum page count.
- Safe HTML parsing without script execution.
- No form submission or login attempts.
- No storage of page HTML, tokens, cookies, authorisation headers, or stack
  traces.
- Safe user-facing errors and sanitised technical logging.

DNS rebinding cannot be fully eliminated between DNS resolution and connection
without infrastructure-level outbound controls. Production deployments should
add egress restrictions or a resolver-pinned transport.

## Screenshots

### Dashboard

Pipeline KPIs, company status distribution, recent companies, and Discovery
Intelligence.

Expected screenshot: `docs/screenshots/dashboard.png`

### Companies

The searchable company directory and lead pipeline workspace.

Expected screenshot: `docs/screenshots/companies.png`

### Discovery

Discovery metrics, filters, scan history, scores, and report actions.

Expected screenshot: `docs/screenshots/discovery.png`

### Discovery Report

Explainable score cards, website health, technology evidence, findings, and
RapidNest Opportunities.

Expected screenshot: `docs/screenshots/discovery-report.png`

Screenshot placeholders are documented in `docs/screenshots/README.md`. Save
future clean product captures at the paths above; captures must contain only the
LeadPilot application and exclude browser chrome, notifications, and unrelated
desktop content.

## Project Structure

```text
LeadPilot-AI-RapidNest/
├── src/leadpilot/
│   ├── application/              # Services and typed application contracts
│   ├── infrastructure/
│   │   ├── database/             # SQLAlchemy models and repositories
│   │   └── discovery_*.py        # Fetching, security, analysis, and scoring
│   └── presentation/streamlit/   # Application shell, pages, theme, and assets
├── migrations/                   # Alembic migration history
├── tests/                        # Unit, persistence, migration, and UI tests
└── docs/screenshots/             # Clean product screenshots
```

## Local Setup

Python 3.12 or newer and Git are required.

### macOS and Linux

```bash
git clone <repository-url>
cd LeadPilot-AI-RapidNest
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m alembic upgrade head
python -m streamlit run src/leadpilot/presentation/streamlit/app.py
```

Open [http://localhost:8501](http://localhost:8501).

### Windows

```powershell
git clone <repository-url>
cd LeadPilot-AI-RapidNest
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
python -m alembic upgrade head
python -m streamlit run src/leadpilot/presentation/streamlit/app.py
```

## Configuration

Copy `.env.example` to `.env` and adjust safe runtime values as needed. The
configuration contains no secrets.

| Variable | Default | Description |
| --- | --- | --- |
| `LEADPILOT_APP_NAME` | `LeadPilot AI` | Application display name. |
| `LEADPILOT_ENV` | `development` | Application environment label. |
| `LEADPILOT_LOG_LEVEL` | `INFO` | Logging threshold. |
| `LEADPILOT_DATABASE_URL` | `sqlite:///./data/leadpilot.db` | SQLAlchemy database URL. |
| `LEADPILOT_DISCOVERY_CONNECT_TIMEOUT` | `5` | HTTP connection timeout in seconds. |
| `LEADPILOT_DISCOVERY_READ_TIMEOUT` | `10` | HTTP read timeout in seconds. |
| `LEADPILOT_DISCOVERY_MAX_PAGES` | `9` | Maximum pages per scan, including the homepage. |
| `LEADPILOT_DISCOVERY_MAX_RESPONSE_BYTES` | `2000000` | Maximum bytes accepted per response. |
| `LEADPILOT_DISCOVERY_USER_AGENT` | `LeadPilot/0.1 Website Discovery` | Public scanner user agent. |
| `LEADPILOT_DISCOVERY_RETRY_COUNT` | `1` | Safe transient retry count. |
| `LEADPILOT_DISCOVERY_SLOW_RESPONSE_MS` | `3000` | Slow-response scoring threshold in milliseconds. |
| `LEADPILOT_AI_ENABLED` | `false` | Enables AI only when a key is also configured. |
| `LEADPILOT_AI_PROVIDER` | `openai` | Provider adapter (`fake` only in development/test). |
| `LEADPILOT_AI_MODEL` | `gpt-5-mini` | Provider model identifier. |
| `LEADPILOT_AI_API_KEY` | empty | Secret read only from the environment; never displayed or stored. |
| `LEADPILOT_AI_TIMEOUT_SECONDS` | `60` | Provider timeout. |
| `LEADPILOT_AI_MAX_RETRIES` | `1` | Safe SDK retry limit. |
| `LEADPILOT_AI_TEMPERATURE` | `0.2` | Reserved provider sampling preference. |
| `LEADPILOT_AI_MAX_OUTPUT_TOKENS` | `6000` | Output budget. |
| `LEADPILOT_AI_INPUT_PRICE_PER_MILLION` | empty | Optional explicit input-token rate. |
| `LEADPILOT_AI_OUTPUT_PRICE_PER_MILLION` | empty | Optional explicit output-token rate. |

Never commit `.env`. For a local key, copy `.env.example`, add the key only to
your ignored `.env`, and set `LEADPILOT_AI_ENABLED=true`. To demonstrate without
network calls, use provider `fake` in a development environment and explicitly
enable AI with a non-production placeholder key.

Cost is estimated only when both rates are configured; otherwise it remains
unavailable. Token usage is shown only as generation metadata.

## Known Limitations

- AI output may be inaccurate and always requires human review.
- Interpretation is limited to structured, website-observable evidence; no
  independent AI browsing or verification of internal systems occurs.
- Scanning and AI generation are synchronous, and provider availability or rate
  limits can affect generation.
- Cost estimates require explicitly configured pricing rates.
- AI content is never automatically sent or published.
- Proposal, PDF, outreach automation, authentication, and multi-user workflows
  are not included in Milestone 5.

## Testing and Quality

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m alembic upgrade head
```

The Milestone 5 build is validated by the repository test suite.

## Roadmap

### Completed

- Milestone 1 — Application Foundation
- Milestone 2 — Company Management
- Milestone 3 — Professional SaaS UI
- Milestone 4 — Website Discovery Engine
- Milestone 4.1 — Dashboard and Discovery UX Polish
- Milestone 5 — AI Discovery Intelligence

### Planned

- Milestone 6 — Proposal Generator
- Milestone 7 — Lead Discovery Agent
- Milestone 8 — CRM and Sales Pipeline
- Milestone 9 — Multi-user SaaS and PostgreSQL deployment

## Known Limitations

- Discovery scans run synchronously.
- JavaScript is not executed.
- Technology detection depends on visible website evidence.
- Dynamic client-rendered content may not be detected.
- Some wide Streamlit tables may require horizontal scrolling.
- DNS rebinding cannot be completely prevented without infrastructure-level
  outbound controls.

## Vision

LeadPilot AI is designed to become an AI-powered sales intelligence platform
that helps consulting teams discover prospects, assess digital maturity,
identify automation opportunities, generate executive discovery insights, and
support the sales journey from research to proposal.

## Built by RapidNest

Built by **RapidNest Software Solutions**

## Multi-tenant organization foundation

LeadPilot stores customer workspaces as Organizations. RapidNest Software
Solutions is seeded as the first active organization, together with its contact
profile, branding reference, and service catalogue. Companies are top-level
organization aggregates; discovery scans and AI analyses also carry an explicit
organization foreign key so repository queries can enforce ownership even when
called outside the UI.

The application resolves an explicit, validated `OrganizationContext`. Repository
instances are bound to that immutable organization ID, and every read, write,
count, update, and delete includes the organization predicate. Archived
organizations are excluded from selection and suspended organizations cannot be
resolved. Streamlit stores only a selection from the server-provided active
organization list; switching clears company, scan, AI, filter, and page state.

The Settings page manages the selected organization profile, safe branding
references, and its ordered active/inactive service catalogue. AI prompts load
the selected brand, contact profile, and active services through the application
persistence boundary. Prospect evidence and organization text are delimited as
untrusted data, and the model is instructed not to invent services or disclose
internal configuration.

### Migration and existing data

Migration `20260728_0005` creates the organization tables, seeds RapidNest, adds
nullable organization keys to existing organization-owned tables, backfills
every existing company, discovery scan, and AI analysis to RapidNest, and only
then makes the keys required and adds foreign keys/indexes. Company name and
website uniqueness are scoped to an organization. No existing lead-intelligence
records are deleted. The SQLite-compatible downgrade returns to the legacy
single-organization schema, but necessarily discards organization metadata and
separation; it is intended only for local rollback.

### Development organization

After upgrading the database, create a distinct local organization without
company data:

```bash
.venv/bin/python -m leadpilot.infrastructure.demo_organization
```

Remove that demo organization and any data deliberately created inside it:

```bash
.venv/bin/python -m leadpilot.infrastructure.demo_organization --remove
```

The demo seed is never run by production migrations.

### Authentication and limitations

This milestone provides tenant-aware data isolation but not production-grade
user authentication. The local organization switcher is a development and
single-user navigation facility; it is not authorization. A future milestone
must map authenticated users to organization memberships and roles before
exposing this deployment to multiple untrusted users. Billing, invitations,
usage limits, per-organization AI credentials, and role administration are also
out of scope.

Organization-controlled text is rendered through normal Streamlit APIs rather
than injected as HTML. Logo references are limited to relative paths below the
approved assets directory, and the existing LeadPilot logo is used for the
RapidNest seed. Secrets remain in environment configuration and are never copied
into organization records or AI prompts.

- Website: [https://www.therapidnest.com](https://www.therapidnest.com)
- Email: [contact@therapidnest.com](mailto:contact@therapidnest.com)
