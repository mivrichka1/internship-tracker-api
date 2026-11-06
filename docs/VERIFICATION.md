# Verification Report

Verified on 6 November 2026. These are observed local results, not a claim of a hosted GitHub Actions run.

| Check | Result |
|---|---|
| Ruff lint | Passed |
| Ruff format check | Passed |
| mypy | Passed, 11 application source files |
| Python compilation | Passed |
| PostgreSQL integration tests in isolated Linux containers | 46 passed, zero skipped |
| Application statement coverage | 98.67% (80% minimum enforced) |
| Migration from empty PostgreSQL to head | Passed |
| Migration downgrade to base, then upgrade to head | Passed on disposable test PostgreSQL |
| Alembic model/schema drift check | No new upgrade operations detected |
| Docker test image build and test Compose command | Passed, exit code 0 |
| Docker runtime image build and application Compose startup | Passed |
| Runtime user | Non-root tracker, UID 10001 |
| API and application PostgreSQL health | Both healthy |
| HTTP smoke scenario | Passed: health, Swagger, registration, login, company, vacancy, application, history, four analytics endpoints, refresh rotation/replay rejection |
| Product scenario with 30 vacancies and 20 submissions | Passed: 14 active, 5 rejections, 1 offer, response rate 0.4, offer rate 0.05 |
| Git staged whitespace validation | Passed |
| Secrets and generated files | .env, virtualenv, caches, temporary data, installer, and output archives excluded from Git |

## Reproduction

```bash
cp .env.example .env
# Set JWT_SECRET and POSTGRES_PASSWORD to unique random values.
docker compose up --build
```

In another terminal:

```bash
docker compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
```

The test database is separate from the application database and has no production data volume. Every test clears only the configured database ending in `_test`. The transaction rollback test deliberately flushes both the status update and history insert before injecting a failure, then verifies that neither write survives. Concurrency tests exercise real PostgreSQL row locks.

## Publication state

Source repository: https://github.com/mivrichka1/internship-tracker-api (branch `main`). GitHub Actions runs on pushes and pull requests; its Actions page is the source of truth for the current hosted result. This report records the local checks performed before publication. The accompanying delivery report records any subsequently observed hosted run.

## Product scope

This deliverable implements the requested backend MVP. It does not claim commercial production traffic, external deployment, email verification, password reset, notifications, rate limiting, or a browser frontend. These are documented future improvements, not placeholder endpoints. Swagger is the interactive API client.
