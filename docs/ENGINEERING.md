# Engineering Notes and Interview Preparation

## Authentication

**Implementation:** passwords use Argon2id through pwdlib. JWT access tokens expire quickly. Refresh tokens have random IDs, typed claims, issuer/audience validation, persisted hashes, rotation, and revocation. Password work runs outside the event loop.

**How components interact:** the API reads OAuth2 form data, the service verifies the account and creates credentials, and the repository loads users or locks refresh rows. The database transaction revokes the previous refresh credential and inserts its replacement together.

**Verify:** register and authorize in Swagger, rotate a refresh token, then try the previous token again. The replay returns 401. Integration tests send two concurrent refresh requests; exactly one succeeds.

**Interview questions:** Why Argon2id? Why hash refresh credentials? Why can a JWT access token remain valid after logout? How does a row lock prevent concurrent replay? How would you revoke all sessions without introducing a token blacklist for every access request?

## Data integrity and ownership

**Implementation:** every private query filters by owner. Composite foreign keys tie a vacancy and company, and an application and vacancy, to the same user. Unique constraints prevent duplicate application records and normalized skill names.

**How components interact:** API authentication determines the user; repository predicates hide foreign records with 404; PostgreSQL independently rejects cross-owner links even if an application bug bypasses the first checks.

**Verify:** create two accounts. Try to read, patch, or delete the other account's resources, attach their company, or query their history. API tests cover these cases and also execute invalid ORM inserts directly against PostgreSQL.

**Interview questions:** Why are UUIDs insufficient authorization? Why are both application checks and database constraints useful? What must be indexed for a composite foreign key? Why return 404 for a foreign resource? What happens on a cascading delete?

## Partial updates and filters

**Implementation:** separate Create, PATCH, Response, and Filter schemas validate the HTTP contract. A PATCH merges supplied fields with the locked current vacancy and validates the complete result. Explicit null clears optional values; missing fields are untouched.

**How components interact:** Pydantic validates syntax and enums. Services enforce cross-field business rules. The repository translates validated filter fields into bound SQL expressions. Response schemas serialize known fields and prevent accidental password/owner leakage.

**Verify:** change only salary_min to exceed salary_max; it returns 422 and leaves the vacancy unchanged. Filter salary ranges with a currency; compare pagination and allowed sort fields. Replace skills with an empty list to clear associations.

**Interview questions:** How does `model_fields_set` or `exclude_unset` differ from `exclude_none`? Why validate the merged PATCH? How do you avoid SQL injection in sorting? Why can't you order mixed-currency salary values without context? How can wildcard search affect index use?

## Application lifecycle and transactions

**Implementation:** stages can be skipped or revisited. Terminal processes need an explicit reopening comment and active target state. Reassigning the current state is idempotent. Submission dates are immutable, and a saved withdrawal is not treated as sent.

**How components interact:** the repository locks the application row. The service changes status, records the first submission if needed, inserts history, and commits once. Request session cleanup rolls back any failure. History position is a generated identity that orders events with the same timestamp.

**Verify:** move applied directly to interview, repeat the request, and inspect history. Then record an offer and reopen with a comment. The rollback test flushes both status UPDATE and history INSERT to PostgreSQL, injects a failure before commit, and verifies neither change is retained.

**Interview questions:** What is atomicity? Why does `flush()` not mean commit? How do two concurrent updates behave under READ COMMITTED? Why do UUIDs and equal timestamps not provide event ordering? Where should a transaction boundary live?

## Analytics

**Implementation:** repository queries aggregate history by application/stage using first and last timestamps. Services compute cohort conversion rates. Counts include only real submissions or recorded stage attainment, rather than inferring skipped stages.

**How components interact:** owner-scoped SQL retrieves real records and aggregated events; service definitions turn them into metrics; response schemas document the result. PostgreSQL `date_trunc` aggregates UTC submission dates for timelines.

**Verify:** the known-data integration test includes four submissions, one saved application, two offers, one rejection, skipped stages, a repeated screening, two submission months, and a withdrawal. It asserts exact rates and a 24-hour first-response average.

**Interview questions:** What is the denominator of response rate? Why is dividing the current interview count by screening count misleading? How do distinct counts handle revisits? What happens after reopening? Why is no observed response time represented as null instead of zero?

## Infrastructure and operations

**Implementation:** Docker Compose runs PostgreSQL and a non-root API image. Database health gates startup; Alembic upgrades run before Uvicorn; container health queries the real database through `/health`; SIGTERM reaches Uvicorn through `exec`. Lifespan cleanup disposes the engine.

**Verify:** run the application Compose command and the independent test Compose command from README. Run `alembic check` to detect model/schema drift. The CI performs these quality checks and a runtime image build. Local test containers have no production database volume.

**Interview questions:** Why use migrations instead of create_all? What is the difference between liveness and readiness? Why is a health check better than a fixed startup sleep? Why use a non-root user and exec? What additional work is needed for internet deployment: HTTPS, secrets management, backups, and rate limiting?

## Deliberate scope choices

One process total per vacancy avoids ambiguous historical cohorts; reopening preserves the first submission date. A shared immutable skill catalogue avoids case duplicates, while the API exposes only skills present in the requesting user's vacancies. There is no separate skill mutation endpoint because skills are attached and replaced through vacancy writes.

No Redis, worker queue, microservices, or browser frontend are required for this MVP. Repository reads are asynchronous, but CPU-expensive password work is offloaded to threads. HTTP request logs contain route templates, method, duration, response code, and a generated request ID; credentials, request bodies, query strings, and SQL exceptions are omitted.
