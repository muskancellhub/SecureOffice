# SecureOffice2

An end-to-end SMB network design + commerce platform. A small business answers a
short intake, the calculator sizes their indoor Wi-Fi / switching / power needs,
the platform picks real SKUs from a unified vendor catalog, generates a
deterministic Bill of Materials and a draw.io topology, captures the lead, and
tracks the design through a demo lifecycle (draft → submitted → installed) with
a monitoring stack and AI avatar concierge on top.

This repo is a monorepo. Each subproject has its own README with deeper detail —
this file is the map.

```
SecureOffice2/
├── backend/      FastAPI + SQLAlchemy API (auth, catalog, BOM, topology, designs, orders…)
├── frontend/     React + Vite + TypeScript app (calculator, design builder, shop, admin)
├── anam_ai/      Small Express + Vite app that hosts the Anam avatar concierge
├── monitoring/   Zabbix + Grafana stack (docker compose)
├── db/           SQL schema + the network vendor catalog Excel workbook
├── docs/         Pitch + supporting docs
├── one-pager.html / .pdf   Marketing one-pager
└── .claude/launch.json     Local "Run" configurations
```

## What it does

- **Network calculator (V1)** — deterministic indoor-Wi-Fi sizing in
  `frontend/src/calculator`. Takes business type, area, users, devices/user,
  throughput, and pricing knobs; returns AP count, switch count, CapEx breakdown.
- **Unified product catalog** — `catalog_items` table is fed from two sources:
  - **PAAPI** (live partner API, via `app/services/papi_client.py`)
  - **Excel vendor catalog** (`db/network_vendor_catalog_*.xlsx`,
    loaded by `app/services/network_vendor_catalog_loader.py`)
- **Deterministic BOM generation** — `network_bom_service.py` turns a calculator
  result into a quoted BOM. Selection is rule-based (category → preferred vendor
  → lowest priced compatible), with derived lines for licenses, cabling, labor,
  and UPS when no SKU exists.
- **Topology + draw.io export** — `network_topology_service.py` emits a
  normalized topology JSON (`Internet → core → switch → APs/endpoints`) and a
  deterministic draw.io XML you can open in any draw.io viewer.
- **Design lifecycle** — saves are mirrored into existing commercial tables:
  `quotes` + `quote_lines`, `tenants` + `tenant_onboarding`, `orders` +
  `workflow_instances`/`workflow_steps`, and `assets` (`design_artifact`).
  Status flow: `draft → reviewed → submitted → in_review → bom_finalized →
  proposal_ready → approved → order_decomposed → fulfillment_in_progress →
  installation_scheduled → installed → completed`.
- **Auth & accounts** — JWT access token (in memory on the client) + `httpOnly`
  refresh cookie. OTP login via SMTP (falls back to console in dev). Google +
  Microsoft OAuth wired through `authlib`. Role-based permissions
  (`SUPER_ADMIN`, `ADMIN`, etc.) with a bootstrap super-admin email.
- **AI concierge avatar** — `anam_ai/` serves an Anam-powered avatar that
  embeds into the frontend (`components/AnamAvatar.tsx`).
- **Monitoring** — `monitoring/docker-compose.yml` brings up Zabbix (server +
  PostgreSQL + agent + nginx web) and Grafana 10 with the Zabbix plugin
  pre-installed. The app surfaces dashboards via `pages/ZabbixPage.tsx`.
- **Chatbot + intake chat** — backend services in `chatbot_service.py` and
  `intake_chat_service.py` (CrewAI for tooling), wired to the React `ChatBot`
  and `BusinessIntakeModal` components.

## Architecture at a glance

```
                       ┌──────────────────────────┐
   Browser ───────────►│  Frontend (Vite, :5173)  │
                       │  React + TypeScript       │
                       └────────────┬─────────────┘
                                    │ REST (axios)
                                    ▼
                       ┌──────────────────────────┐
                       │   Backend (FastAPI, :8000)│
                       │   routers → services →   │
                       │   repositories → ORM     │
                       └────┬───────────────┬─────┘
                            │               │
                  ┌─────────▼──┐     ┌──────▼─────────┐
                  │  SQLAlchemy │    │  External APIs │
                  │  (Postgres  │    │  PAAPI, OAuth, │
                  │   / SQLite) │    │  SMTP/SendGrid,│
                  └─────────────┘    │  CDW, Zabbix,  │
                                     │  OpenAI/Crew   │
                                     └────────────────┘

   anam_ai (:5001)  ──►  embedded as <iframe>/component in frontend
   Zabbix (:8080)   ──►  embedded via Grafana iframes (Grafana :3000)
```

Backend layering (consistent across modules): `routes/` (HTTP) → `services/`
(business logic) → `repositories/` (DB access) → `models/` (SQLAlchemy ORM) →
`schemas/` (Pydantic IO).

## Ports used

| Service                  | Port | Notes                                   |
|--------------------------|------|------------------------------------------|
| Backend (FastAPI)        | 8000 | `uvicorn app.main:app --reload --port 8000` |
| Frontend (Vite)          | 5173 | `npm run dev` in `frontend/`             |
| Anam avatar app          | 5001 | `npm run dev` in `anam_ai/`              |
| One-pager preview        | 8099 | `python3 -m http.server 8099` at root    |
| Grafana                  | 3000 | docker compose, in `monitoring/`         |
| Zabbix UI                | 8080 | docker compose, in `monitoring/`         |
| Zabbix server (agents)   |10051 | docker compose, in `monitoring/`         |

## Quick start

Prereqs: **Python 3.11**, **Node 20+**, and optionally **Docker** for the
monitoring stack.

```bash
git clone https://github.com/muskancellhub/SecureOffice.git SecureOffice2
cd SecureOffice2
```

### 1. Backend (port 8000)

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit secrets / DATABASE_URL / SMTP / OAuth
uvicorn app.main:app --reload --port 8000
```

API docs (non-prod only): `http://localhost:8000/docs`.

If `DATABASE_URL` is empty the app falls back to the local SQLite file
`backend/secureoffice2.db`. For real use, point it at Postgres.

### 2. Frontend (port 5173)

```bash
cd frontend
cp .env.example .env        # set VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev
```

### 3. Anam avatar (optional, port 5001)

```bash
cd anam_ai
npm install
npm run dev
```

### 4. Monitoring stack (optional, Docker)

```bash
cd monitoring
docker compose up -d
#  Zabbix UI  → http://localhost:8080   (Admin / zabbix)
#  Grafana    → http://localhost:3000   (admin / admin)
```

### 5. One-pager preview (optional, port 8099)

```bash
python3 -m http.server 8099
# open http://localhost:8099/one-pager.html
```

## Environment variables (highlights)

See `backend/.env.example` and `frontend/.env.example` for the full list.

**Backend** (`backend/.env`):

- `APP_ENV` — `development` | `production`. Production refuses to start unless
  `COOKIE_SECURE=true`, a distinct `OAUTH_SESSION_SECRET` is set, and
  `APP_DEBUG=false` (see `_assert_production_hardening` in `app/main.py`).
- `DATABASE_URL` — Postgres URL; blank = local SQLite.
- `JWT_SECRET_KEY`, `OAUTH_SESSION_SECRET` — must be long, random, and distinct.
- `BACKEND_CORS_ORIGINS` — comma-separated, e.g. `http://localhost:5173`.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL`, `SMTP_USERNAME`, `SMTP_PASSWORD`
  — OTP email transport.
- `SENDGRID_API_KEY` — used by order-capture notifications when set.
- `GOOGLE_CLIENT_ID/SECRET`, `GOOGLE_REDIRECT_URI`,
  `MICROSOFT_CLIENT_ID/SECRET`, `MICROSOFT_REDIRECT_URI` — OAuth providers.
- `BOOTSTRAP_SUPER_ADMIN_EMAIL` — auto-promotes that user to `SUPER_ADMIN` on
  startup.
- `PAPI_BASIC_AUTH_TOKEN` — enables PAAPI sync at startup.
- `CDW_INGEST_MODE` — `script` (uses `CDW_AGENT_COMMAND`, `CDW_QUERY`,
  `CDW_LIMIT`) or `openai` (uses `OPENAI_API_KEY`, `CDW_OPENAI_MODEL`).
- `DESIGN_HANDOFF_EMAIL` — where submitted-design notifications go.

**Frontend** (`frontend/.env`):

- `VITE_API_BASE_URL=http://localhost:8000`
- `VITE_GRAFANA_URL=http://localhost:3000`

## Selected API surface

Mounted by `backend/app/main.py`. Non-exhaustive — see `backend/app/routes/`
for the full list.

- `GET /health`
- Auth: `POST /auth/login/otp/request`, `POST /auth/login/otp/verify`,
  `POST /auth/refresh`, `/auth/google/*`, `/auth/microsoft/*`
- Users: `GET /users/me`, admin user management routes
- Catalog: `GET /catalog`, `GET /catalog/{item_id}` (ID or SKU lookup)
- Integrations:
  - `POST /integrations/cdw/sync-routers`
  - `POST /integrations/network/sync-vendor-catalog`,
    `GET /integrations/network/last-sync`
  - `POST /integrations/network/generate-bom`
  - `POST /integrations/network/generate-topology`
- Designs: `POST /designs`, `GET /designs`, `GET /designs/{id}`,
  `POST /designs/{id}/submit`, `GET /designs/ops/submissions`,
  `PATCH /designs/{id}/status`
- Cart: `GET /cart`, `POST /cart/lines`
- Orders / quotes / pricing / billing / lifecycle / onboarding / chatbot / zabbix
  / intake-chat — see corresponding router modules.

## Tests

Backend:

```bash
cd backend
source .venv/bin/activate
pytest
```

Frontend:

```bash
cd frontend
npm test          # vitest run
npm run test:watch
```

Notable backend suites: `tests/test_network_design_service.py`,
`tests/test_network_topology_service.py`,
`tests/test_unified_catalog_and_bom.py`,
`tests/test_network_vendor_catalog_loader.py`.

## Security notes

- Production startup is guarded — see `_assert_production_hardening` in
  `app/main.py`. Insecure defaults make the server refuse to boot.
- Auto-generated API docs (`/docs`, `/redoc`, `/openapi.json`) are disabled in
  production.
- Middleware order (outermost → innermost): CORS → AuthContext → Security
  headers → Rate limit → Session.
- Refresh tokens live in `httpOnly` cookies; access tokens are kept in memory
  on the client (`AuthContext`).
- A demo vendor account (`vendor@gmail.com` / `vendor123`) is seeded **only**
  when `APP_ENV != production`.

## Repo conventions

- Each subproject (`backend/`, `frontend/`) has its own README with deeper
  module-level notes (BOM generation rules, topology grouping rules, calculator
  formulas, demo lifecycle, retrieval-ready pipeline, etc.).
- Run configs for the IDE / `claude` runner live in `.claude/launch.json`.
- `.gitignore` excludes `.env*` (except `*.env.example`), virtualenvs,
  `node_modules`, and build artifacts.

## License

Proprietary — internal project. Not for redistribution.
