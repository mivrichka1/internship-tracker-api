# Portfolio Wording

## GitHub repository description

Async FastAPI/PostgreSQL API for tracking internships and hiring pipelines, with JWT session rotation, tenant-safe relational constraints, historical funnel analytics, Docker Compose, and PostgreSQL integration tests.

## Resume — English

- Built an asynchronous internship-tracking REST API with FastAPI, SQLAlchemy 2, asyncpg, PostgreSQL, and Alembic, using separate API, service, and repository layers.
- Implemented Argon2id authentication and rotating, revocable refresh credentials, including PostgreSQL row locking to prevent concurrent token replay.
- Enforced per-user data isolation with owner-scoped queries and composite foreign keys; implemented atomic application status/history updates and historical hiring-funnel analytics.
- Added PostgreSQL integration tests covering authorization, concurrency, transaction rollback, CRUD, validation, and metric calculations; automated linting, type checks, migrations, coverage, and container builds in GitHub Actions.

## Резюме — русский

- Разработала асинхронный REST API для учёта стажировок и этапов отбора на FastAPI, SQLAlchemy 2, asyncpg и PostgreSQL с миграциями Alembic и разделением API, сервисов и SQL-запросов.
- Реализовала Argon2id-аутентификацию, JWT и ротацию refresh-токенов с отзывом и защитой от конкурентного повторного использования через блокировки PostgreSQL.
- Обеспечила изоляцию пользователей на уровне запросов и составных внешних ключей; реализовала транзакционную историю статусов и расчёт воронки по фактически пройденным этапам.
- Подготовила интеграционные тесты на отдельной PostgreSQL, Docker Compose и GitHub Actions для проверки типов, стиля кода, миграций, покрытия и сборки контейнера.

## Interview introduction

“I built a personal application tracker because a spreadsheet becomes hard to manage when hiring processes branch, skip stages, and reopen. The most interesting parts were making status and history atomic, protecting tenant relationships in PostgreSQL, serializing refresh rotation, and defining conversions without counting skipped stages as passed. I tested these behaviours against a real PostgreSQL database, including simultaneous requests and rollback after flushed writes.”

## Evidence and limits

Use the verification report accompanying the source archive for the measured test count and coverage of the delivered revision. Distinguish local successful checks from an actual GitHub Actions run: a local build does not prove that a remote workflow has executed. This project is a portfolio application, not a claim of commercial traffic, production scale, or team deployment experience.
