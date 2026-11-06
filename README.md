# Internship Tracker API

An asynchronous REST API for organizing internship opportunities, applications, hiring stages, notes, and job-search analytics. Built as a Python backend portfolio project with a real PostgreSQL database, documented HTTP contracts, transaction-safe status history, and integration tests.

## Features

- Registration, Argon2id password hashing, JWT access tokens, rotating and revocable server-side refresh credentials.
- Private company and vacancy CRUD with owner isolation enforced both in queries and composite database foreign keys.
- Search, validated sorting, bounded pagination, salary/currency, skill, deadline, work format, company, and application-status filters.
- Case-insensitive shared skill normalization and a user-scoped skills catalogue.
- Application notes, next-action dates, flexible hiring stages, explicit reopening, and atomic status history.
- Overview, historical stage funnel, skill frequency, UTC application timelines, and mean time to first recorded employer response.
- Alembic migrations, JSON request logs without credentials, standardized errors, readiness checks, graceful shutdown, non-root Docker runtime, and GitHub Actions checks.

## Tech Stack

Python 3.12+, FastAPI, Uvicorn, SQLAlchemy 2, asyncpg, PostgreSQL 16, Alembic, Pydantic 2, pydantic-settings, PyJWT, pwdlib/Argon2id, pytest/pytest-asyncio/HTTPX, pytest-cov, Ruff, mypy, Docker Compose.

## Architecture

This is a modular monolith. The files are grouped by responsibility without one-file-per-entity boilerplate:

```text
app/
  main.py             # HTTP routes, dependency injection, response models, error handlers
  schemas.py          # Create, PATCH, response and query-parameter schemas
  services.py         # Business rules, status transitions, token rotation, transactions
  repository.py       # Owner-scoped SQL, filters, eager loading and aggregations
  models.py           # Relational models and constraints
  db.py               # Async engine, sessions and rollback
  config.py           # Validated environment configuration
  core/security.py    # Argon2id, JWT claims and token hashing
  core/errors.py      # HTTP-independent domain errors
alembic/versions/     # Versioned schema evolution
tests/               # Integration tests against dedicated PostgreSQL
compose.test.yml     # Isolated test database and test runner
```

Routes delegate to the service layer for writes and business rules. Read-only routes may call the repository directly. Services own commits; a failure rolls back the request session. PostgreSQL row locks serialize refresh rotation and application changes. Relationships needed for vacancy responses use `selectinload` to avoid per-row lookups. Authentication password hashing and verification run in a worker thread to keep the event loop responsive.

## Database Schema

All primary identifiers are UUIDs. Database timestamps are timezone-aware and sessions use UTC. History also has a generated `position` so simultaneous status events have a stable order.

```mermaid
erDiagram
  USERS ||--o{ COMPANIES : owns
  USERS ||--o{ VACANCIES : owns
  USERS ||--o{ APPLICATIONS : tracks
  USERS ||--o{ REFRESH_TOKENS : holds
  COMPANIES ||--o{ VACANCIES : lists
  VACANCIES ||--o{ VACANCY_SKILLS : tagged
  SKILLS ||--o{ VACANCY_SKILLS : referenced
  VACANCIES ||--o| APPLICATIONS : has
  APPLICATIONS ||--o{ APPLICATION_HISTORY : records
```

- Companies belong to individual users; names are unique per owner.
- Vacancies reference `(company_id, user_id)` to prevent foreign-owner links, even outside the API.
- Applications reference `(vacancy_id, user_id)` and are unique per owner/vacancy. V1 permits **one process total**, including terminal processes; reopen the existing process rather than creating a duplicate. Deleting an application removes its history.
- Skills are unique by trimmed Python `casefold()` normalization. The association table has a composite primary key, so a skill appears once per vacancy.
- Salary bounds must be nonnegative and ordered; any salary requires a three-letter uppercase currency.
- Deleting a company cascades through its vacancies, applications, history, and skill associations. Shared skill records remain. Deleting a user cascades through their private data and refresh credentials.

## Getting Started

Install Docker Desktop (macOS/Windows) or Docker Engine with the Compose plugin (Linux).

```bash
cp .env.example .env
# Replace JWT_SECRET (at least 32 characters) and POSTGRES_PASSWORD with unique random values.
# Use a hexadecimal password so it is safe inside the database URL.
# For example, generate one with: openssl rand -hex 32
docker compose up --build
```

The database health check gates API startup. The API applies Alembic migrations before starting Uvicorn. PostgreSQL data persists in a named volume.

- [Swagger UI](http://localhost:8000/docs)
- [ReDoc](http://localhost:8000/redoc)
- [OpenAPI JSON](http://localhost:8000/openapi.json)
- [Database readiness](http://localhost:8000/health)

In Swagger: register first, click **Authorize**, enter your email as `username` and your password, then create a company, vacancy, and application. Tokens from the login endpoint can also be used as `Authorization: Bearer <access_token>`.

Stop with `docker compose down`. This preserves the application database volume.

### Local development

Use Python 3.12+ and a local PostgreSQL instance:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
# Set DATABASE_URL in .env to your local postgresql+asyncpg URL.
alembic upgrade head
uvicorn app.main:app --reload --no-access-log
```

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Async PostgreSQL URL for local tools; Compose builds its own URL from POSTGRES variables | Required for local tools |
| `POSTGRES_USER` | Compose database user | tracker |
| `POSTGRES_PASSWORD` | Compose database password (use a random URL-safe/hex value) | Required |
| `POSTGRES_DB` | Compose application database name | tracker |
| `JWT_SECRET` | HS256 signing secret, at least 32 characters | Required |
| `ACCESS_TOKEN_MINUTES` | Access lifetime, 1–1440 minutes | 15 |
| `REFRESH_TOKEN_DAYS` | Refresh lifetime, 1–365 days | 30 |
| `APP_ENV` | `development`, `test`, or `production` | development |
| `TEST_DATABASE_URL` | Dedicated PostgreSQL URL for pytest, database name must end in `_test` | Required for integration tests |

`.env` is ignored by Git and excluded from Docker images. The example credentials must be replaced before public deployment; also provision HTTPS and managed secrets. When running local Alembic outside Compose, keep DATABASE_URL consistent with your database credentials. CORS is disabled by default because this backend has no cross-origin browser frontend.

## Authentication and Sessions

Login uses the standard OAuth2 password form (`username` contains the email). JWT claims contain a subject, token type, expiration, random token ID, issuer, and audience. JWTs contain no email, name, or password.

Only a SHA-256 digest of each high-entropy signed refresh token is stored. Successful refresh locks and revokes the old credential and creates its replacement in one transaction. Concurrent use of a refresh token can succeed only once. Logout idempotently revokes the supplied credential belonging to the authenticated user. Access tokens remain valid until their short expiration; logout does not maintain an access-token blacklist. Other devices' refresh credentials remain independent. Signing out every session is a future enhancement.

## API Documentation

Every private endpoint requires a Bearer token. The OpenAPI document provides request/response schemas, enums, required fields, and OAuth2 authorization.

| Resource | Endpoints |
|---|---|
| Authentication | `POST /api/v1/auth/register`, `/login`, `/refresh`, `/logout` |
| Current user | `GET /api/v1/users/me` |
| Companies | `POST/GET /api/v1/companies`; `GET/PATCH/DELETE /api/v1/companies/{id}` |
| Vacancies | `POST/GET /api/v1/vacancies`; `GET/PATCH/DELETE /api/v1/vacancies/{id}` |
| Skills | `GET /api/v1/skills` (skills used by the current user, optional `search` and `limit`) |
| Applications | `POST/GET /api/v1/applications`; `GET/PATCH/DELETE /api/v1/applications/{id}` |
| Status/history | `PATCH /api/v1/applications/{id}/status`; `GET /api/v1/applications/{id}/history` |
| Analytics | `GET /api/v1/analytics/overview`, `/funnel`, `/skills`, `/timeline` |

List responses use `{ "items": [...], "total": 0, "page": 1, "page_size": 20 }`. Pages start at 1, with a maximum of 100 items. Sorting uses explicit allowlists, a stable UUID tie-breaker, and nulls last.

Vacancy filters: `search` (title), `company` (company name), `company_id`, `skill`, `work_format`, `salary_min`, `salary_max`, `currency`, `application_deadline_before`, `application_deadline_after`, `status`, `sort`, `direction`, `page`, `page_size`. `status_filter` is an alias retained for compatibility. Salary filters find overlapping advertised ranges: maximum offered pay must meet the requested minimum, and minimum offered pay must not exceed the requested maximum. A one-sided advertised range uses its known bound. Currency is required for salary filtering or salary sorting; no exchange-rate conversion is performed. Missing salary bounds do not match numeric filters.

Company lists support `search`, `location`, `industry`, `sort=name|created_at`. Application lists support `status`, `vacancy_id`, title `search`, and sorting by `created_at`, `applied_at`, or `next_action_at`.

### PATCH and status rules

Omitted fields are unchanged. Explicit `null` clears optional fields such as descriptions, links, notes, dates, and salary bounds. Required fields such as title, company, work format, and the skills list reject `null`. An empty skills list clears the association. The merged vacancy is validated, so changing only one salary bound cannot create an invalid range. Unknown body and query fields are rejected.

`PATCH /applications/{id}` changes only notes and next-action dates; use the dedicated status endpoint for transitions. Timestamps supplied by callers require a UTC offset. `applied_at` is set on first submission and remains the first submission date after reopening. It cannot be in the future or accompany a newly saved application.

Statuses are `saved`, `applied`, `screening`, `assessment`, `interview`, `offer`, `rejected`, and `withdrawn`. Active stages can be skipped or revisited. A sent process cannot return to `saved`. A withdrawal from `saved` is not counted as a submission. Moving directly from `saved` to an employer-response stage also records the submission event. Reassigning the current status produces no history. Reopening a terminal state requires `reopen: true`, a nonblank comment, and a nonterminal sent status. Status and history commit atomically.

### Errors

```json
{"error":{"code":"VACANCY_NOT_FOUND","message":"Vacancy was not found"}}
```

400 indicates a missing required filter context; 401 invalid/missing authentication; 403 is supported by the common HTTP handler; 404 also hides foreign-owned resources; 409 indicates duplicates or a forbidden lifecycle transition; 422 indicates invalid input. Database outages return 503; unexpected failures return a sanitized 500. Validation responses identify fields without echoing request values. Passwords, tokens, SQL, and stack traces are not included in responses or request logs.

## Analytics Definitions

- **total_vacancies:** all saved vacancy records.
- **total_applications:** records with an actual `applied_at`; excludes saved-only records and withdrawals before submission.
- **active_applications:** sent processes currently outside terminal states.
- **rejected / offers:** sent processes currently in that terminal status.
- **response_rate:** sent processes with at least one recorded screening, assessment, interview, offer, or rejection event, divided by all submitted processes. A later withdrawal or reopening does not erase a recorded employer response. A rejection is an explicit user-recorded employer response; automatic inference from silence is never used.
- **offer_rate:** current offers divided by all submitted processes.
- **average_response_hours:** mean time between submission and first recorded employer-response event. Processes with no such event are excluded. Returns `null` when no response times exist.

Zero rate denominators produce `0`. A missing event is never invented.

The funnel returns stages Applied → Screening → Assessment → Interview → Offer. `count` is the number of distinct applications that actually reached each stage; repeated visits count once and skipped stages remain absent. Applied counts all sent processes. `conversion_from_applied` divides by all submissions. `progressed_from_previous` counts applications that have both stages in chronological order. `conversion_from_previous` divides that cohort by all applications that reached the preceding stage; it cannot exceed 1, even when stages are skipped or revisited.

Skills analytics counts distinct vacancies per normalized skill. Timeline uses immutable first-submission dates, PostgreSQL `date_trunc`, UTC day/week/month buckets, and Monday-start weeks. Empty buckets are omitted.

## Example Requests

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"dev@example.com","password":"a-long-example-password","full_name":"Dev Student"}'

curl -X POST http://localhost:8000/api/v1/auth/login \
  -d 'username=dev%40example.com&password=a-long-example-password'

# Set TOKEN to the returned access_token, then create a company:
curl -X POST http://localhost:8000/api/v1/companies \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Example Labs","website_url":"https://example.com"}'

# Substitute the returned company UUID:
curl -X POST http://localhost:8000/api/v1/vacancies \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"company_id":"COMPANY_UUID","title":"Python Backend Intern","skills":["Python","FastAPI","PostgreSQL"],"work_format":"remote","salary_min":80000,"currency":"RUB"}'

curl 'http://localhost:8000/api/v1/vacancies?skill=Python&salary_min=80000&currency=RUB&work_format=remote' \
  -H "Authorization: Bearer $TOKEN"

curl -X POST http://localhost:8000/api/v1/applications \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"vacancy_id":"VACANCY_UUID","status":"applied"}'

curl -X PATCH http://localhost:8000/api/v1/applications/APPLICATION_UUID/status \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"status":"interview","comment":"Recruiter invited me"}'

curl http://localhost:8000/api/v1/analytics/overview -H "Authorization: Bearer $TOKEN"
```

## Database Migrations

```bash
docker compose exec api alembic current
docker compose exec api alembic check
# Local development:
alembic upgrade head
alembic revision --autogenerate -m "describe schema change"
```

Review generated migrations before applying them. The application never creates tables using `create_all()`. Existing databases upgrade through versioned migrations. Migration downgrade/upgrade round trips are checked only on a disposable test database.

## Running Tests

Run the complete PostgreSQL integration suite in isolated containers with one command:

```bash
docker compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
```

The test Compose project uses a separate PostgreSQL database and does not mount the application's production data volume. Test fixtures reject databases whose names do not end in `_test`; fixtures truncate only the explicitly configured test database before each test. Do not point tests at a database containing valuable data.

For an existing local test PostgreSQL database:

```bash
pip install -e '.[dev]'
export TEST_DATABASE_URL=postgresql+asyncpg://tracker:tracker@localhost:55432/tracker_test
DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head
pytest --cov=app --cov-report=term-missing
ruff check .
ruff format --check .
mypy app
```

The suite covers authentication expiry, rotation/revocation, concurrent refresh and status changes, CRUD, filters, PATCH/null rules, normalized skills, two-user resource isolation, database tenant constraints, terminal reopening, transactional rollback after flushed status/history updates, and known analytics datasets with skipped/repeated stages and different dates. Coverage enforces a minimum of 80%; meaningful assertions take priority over the percentage.

## CI/CD

GitHub Actions runs on pushes and pull requests: Python setup, dependency installation, Ruff lint, format check, mypy, PostgreSQL health checks, Alembic upgrades and model/schema drift checks, pytest with coverage, and a Docker runtime build. It performs validation and image building; it does not deploy the application or publish images. A workflow result exists only after the repository is pushed to GitHub.

## Learning and Portfolio

See [engineering notes and interview questions](docs/ENGINEERING.md) and [resume/GitHub wording](docs/PORTFOLIO.md).

## Future Improvements

Email verification and password reset; auth rate limiting; revoke-all-sessions controls; optional reminder delivery; exports; per-company/work-format analytics; query-plan benchmarking for larger datasets; deployment behind HTTPS and managed PostgreSQL backups. No Redis, queues, or microservices are needed for the current scope.
