# PrivaCheck M8.3 — Integration testing

This stage validates the authenticated API-to-persistence-to-queue handoff,
scan ownership boundaries, and the live worker workflow.

## Automated integration tests

Run from the project root after installing the normal project requirements and
`requirements-auth.txt`:

```powershell
python -m pytest tests\integration\test_authenticated_scan_workflow.py -q
```

The new tests use an isolated in-memory SQLite database and a recording Celery
producer. They exercise the real FastAPI app, authentication service, session
lookup, asynchronous scan service, repositories and owner-scoped endpoints.
They do not connect to, mutate, or drop the developer's PostgreSQL database.
They do not start Playwright or worker processes.

Run the complete regression suite afterward:

```powershell
python -m pytest -q
```

## Live multi-process smoke test

The live smoke test is intentionally performed against the developer's local
PostgreSQL and Valkey services, because a unit/integration test with a fake
producer cannot prove that independent Celery processes are exchanging tasks.

Keep these services running in separate terminals:

1. PostgreSQL
2. Valkey
3. FastAPI
4. Crawler worker listening to `crawler.scan`
5. Compliance worker listening to `compliance.evaluate`
6. React/Vite frontend

Verify both workers respond to Celery remote control:

```powershell
python -m celery -A backend.services.crawler_service.celery_app:crawler_celery_app inspect ping
python -m celery -A backend.services.compliance_service.celery_app:compliance_celery_app inspect ping
```

Expected: both worker nodes return `pong`.

Then, using two separate browser profiles (or one normal and one private
window):

1. Register account A and submit a scan.
2. Confirm account A sees its scan in history and can open its report after it
   reaches `COMPLETED`.
3. Register account B in the other browser profile.
4. Confirm account B's history does not contain account A's scan.
5. Copy account A's scan URL into account B's browser. Both status and report
   endpoints must return a not-found response, not the report.
6. Log out account A. Refreshing a protected page must return to the login flow.
7. Log account A back in and verify the report and JSON/PDF exports still work.

## Worker outage behaviour observed during development

Celery's `send_task` can enqueue successfully even if no worker is currently
consuming that queue. The API therefore cannot infer worker availability just
from a successful enqueue. In local development, keep both worker processes
running. A queued/running scan that remains stuck should be diagnosed by
checking queue consumers and worker logs before resubmitting it.

This runbook deliberately does not implement automatic stale-scan failure or
replay. That requires a separate recovery design with idempotency and worker
lease semantics; blindly marking a long-running scan failed can race a worker
that is still processing it.

## Acceptance criteria

- Anonymous scan endpoints return `401`.
- Scan creation requires a valid authenticated session and CSRF token.
- A scan is persisted with the authenticated user's UUID.
- Queue messages contain scan metadata only, not browser session secrets or
  account passwords.
- Account A can list, inspect and retrieve its own scan report.
- Account B receives an empty history and `404` for Account A's scan status and
  report.
- Logout revokes the session and protected endpoints reject it.
- The live crawler-to-compliance flow finishes with both worker processes
  online.
- JSON and PDF export work from the owner's completed report.
