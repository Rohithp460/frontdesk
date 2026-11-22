# Frontdesk

Frontdesk is an agent-facing customer support ticket application for Arvo
Systems. It provides authenticated ticket ownership, customer-visible replies,
team-only notes, SLA deadlines, and an append-only ticket timeline.

## Project links

- **Live URL:** Not deployed.
- **Repository URL:** <https://github.com/Rohithp460/frontdesk.git>

## Tech stack

- React, Vite, TypeScript, Tailwind CSS, Axios, and React Router
- Python, FastAPI, SQLAlchemy 2, and Alembic
- MySQL 8 with `utf8mb4`
- JWT authentication and bcrypt password hashes
- Docker Compose and pytest

## Implemented features

- Agent/admin login and active-account checks.
- Ticket creation, list/search/filter, details, assignment by claim, priorities,
  and lifecycle actions.
- Customer-visible replies and team-only internal notes.
- UTC storage and working-hour SLA calculations in Asia/Kolkata.
- Weekend/holiday-aware deadlines, customer wait periods, SLA status, and
  deterministic audit timelines.
- Demo-only simulated customer replies and agent reopen action.
- Admin-only manual SLA-miss and auto-close triggers.
- MySQL-locked public-reference allocation and ticket lifecycle transitions.

## Business rules and assumptions

The decisions and ambiguous behavior are documented in [DECISIONS.md](./DECISIONS.md).
Key rules:

- Store timestamps in UTC. Interpret naive database datetimes as UTC, never as
  Kolkata wall time.
- Working hours are 09:30-18:30 Asia/Kolkata, Monday-Friday, excluding dates
  marked as holidays/non-working in the business calendar.
- The working interval ends at 18:30; 18:30 itself has no remaining time that
  day.
- Only the assigned agent or an admin may manage an assigned ticket. Any active
  agent may view tickets or claim an unassigned ticket.
- Repeated/invalid resolve and close transitions return HTTP 409.
- Application actions treat event history as append-only; ticket deletion is
  restricted while event or wait history exists. Production database access
  should also restrict direct updates/deletes to audit tables.
- The agent-authenticated reopen and customer-reply routes are demo flows, not
  customer authentication. Their event actors reflect the simulated actor.
- Admins run auto-close manually using `POST /api/v1/admin/auto-close-check`.
  Production requires a scheduler to invoke this and `POST
  /api/v1/admin/sla-check`.

## Local setup

### Docker Compose (recommended)

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

Compose starts MySQL, applies Alembic migrations in the backend container, then
starts Uvicorn. Local URLs:

- Frontend: <http://localhost:5173>
- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

The Compose file has development-only database credential defaults. Do not use
them in a public deployment.

### Backend without Docker

Set `MYSQL_SERVER=localhost` and either unset `DATABASE_URL` or change its host
to `localhost` in `backend/.env`, install dependencies, and run:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend without Docker

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Environment variables

Backend settings are in `backend/.env.example`; create `backend/.env` for local
use. Production must supply:

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | Set to `production` to enable production validation |
| `JWT_SECRET` | Required strong random secret, at least 32 characters |
| `ALGORITHM` | JWT signing algorithm (default `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime |
| `DATABASE_URL` | SQLAlchemy URL for MySQL |
| `MYSQL_SERVER`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB` | MySQL connection settings when `DATABASE_URL` is unset |
| `CORS_ORIGINS` | JSON array or comma-separated browser origins; set production domains explicitly |
| `PROJECT_NAME` | API title |

`VITE_API_BASE_URL` is the frontend API origin, without `/api/v1`. Docker passes
it as a frontend build argument; rebuild the frontend image after changing it.
Never deploy with the development-only generated JWT secret or demo passwords.
Production startup requires `DATABASE_URL`, a strong `JWT_SECRET`, and explicit
HTTPS `CORS_ORIGINS`. The frontend login page does not contain demo credentials.

## Migrations and seed data

Manual migration command:

```bash
cd backend
alembic upgrade head
```

Docker startup performs this command before Uvicorn. Create demo agents after
the database is available:

```bash
cd backend
python scripts/seed.py
```

Demo credentials (local development only):

- Admin: `meera@arvo.example` / `Admin@1234`
- Agent: `priya@arvo.example` / `Agent@1234`
- Agent: `arjun@arvo.example` / `Agent@1234`

Do not seed these credentials into production; create unique accounts and
rotate/remove any demo accounts.

For the first production account, run `scripts/seed.py` once with
`ENVIRONMENT=production`, `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`, and
`FRONTDESK_BOOTSTRAP_NAME`, `FRONTDESK_BOOTSTRAP_EMAIL`, and
`FRONTDESK_BOOTSTRAP_PASSWORD` set in the execution environment. Optionally set
`FRONTDESK_BOOTSTRAP_ROLE=AGENT`; it defaults to `ADMIN`. The production seed
creates only the explicitly supplied account and skips an existing email.
Remove the bootstrap password variable after use. Customer records must be
imported or inserted through a trusted database operation; there is no customer
management API.

## API overview

The same API routers are available under `/api/v1` and at the root for local
compatibility. Main endpoints include:

- `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `GET|POST /api/v1/tickets`, `GET /api/v1/tickets/{id}`
- `POST /api/v1/tickets/{id}/claim`, `/replies`, `/internal-notes`,
  `/resolve`, `/close`
- Demo-only `POST /api/v1/tickets/{id}/customer-reply` and `/reopen`
- Admin-only `POST /api/v1/admin/sla-check` and `/auto-close-check`

See Swagger at `/docs` for request/response schemas and filters.

## Railway deployment

Deploy three Railway services: MySQL, backend, and frontend. Do not use
development Compose credentials in Railway.

1. Create a Railway MySQL service and use its private connection URL as the
   backend `DATABASE_URL`.
2. Deploy the backend from the repository with root directory `backend` and
   its Dockerfile. Configure `ENVIRONMENT=production`, a generated
   `JWT_SECRET` (`openssl rand -hex 32`), `DATABASE_URL`, and
   `CORS_ORIGINS`. The backend entrypoint applies Alembic migrations before
   starting Uvicorn and listens on Railway's `PORT`.
3. Deploy the frontend with root directory `frontend` and its Dockerfile.
   Provide `VITE_API_BASE_URL` at build time as the backend's public HTTPS
   origin, without `/api/v1`. The Nginx service listens on port 80.
4. Generate Railway HTTPS domains for the frontend and backend. Set backend
   `CORS_ORIGINS` to the exact frontend origin, then redeploy the backend.
5. Bootstrap an admin once using the production seed environment variables
   described above. Import real customer records through a trusted database
   operation before creating tickets.
6. Configure backups and a Railway scheduled job if automatic response-SLA
   checks and auto-close are required. No scheduler is included in this app.

The backend Docker build excludes local `.env` files. Store all production
secrets in Railway Variables, never in the repository or container build
context. Verify `/health` after deployment. The live URL remains unconfigured
until Railway generates the production domain.

Docker Compose remains a local-development option. Its default database
credentials are development-only.

## Tests

```bash
cd backend
python -m pytest
```

```bash
cd frontend
npm run build
```

## Known limitations and unfinished work

- No live deployment URL is configured yet.
- The customer-reply and reopen routes are demo-only agent-authenticated
  simulations; there is no customer login or inbound email integration.
- Customer creation/import is an operational database task; no customer
  management endpoint is included.
- Auto-close and response-SLA expiration require an external scheduler in
  production.
- Holiday dates must be maintained in the business calendar.
- ORM-level guards prevent application updates/deletes to ticket events, but
  direct database administrators can bypass ORM protections. Production
  database credentials should be least-privilege.
- Production monitoring, infrastructure-managed secret rotation, and customer
  account flows are not included.

The following are intentionally unfinished because this submission is scoped
to the core agent ticket workflow: customer portal/authentication, email or
WhatsApp notifications, file attachments, manager dashboards, reports, an
admin UI, holiday-management UI, advanced search, and bulk actions. They need
separate product, security, and operational requirements and are not represented
as implemented features here.
