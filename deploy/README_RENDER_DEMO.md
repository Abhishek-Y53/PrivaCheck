# PrivaCheck Render Free demonstration — implementation guide

**Scope:** One Free Render web service (React + FastAPI), one Free Render
PostgreSQL, one Free Render Key Value, and TWO laptop-hosted Celery workers.
No change to `docker-compose.yml` or existing volumes is required.

## Important resource/billing limits

- Free Postgres has **1 GB** and **expires after 30 days**. It has no managed backup.
- Free Key Value has **25 MB**, **no persistence**, and its queued tasks are
  lost if Render restarts it. Use `noeviction` to avoid deleting queued jobs
  under pressure; when full, task publishing may fail instead.
- Free web service sleeps after 15 minutes idle; it has 512 MB RAM.
- Render's free web service has no Shell and no one-off jobs. Run Alembic
  from your laptop with explicit REMOTE database credentials.
- Render may bill for over-limit bandwidth; review Dashboard usage and do not
  add payment details for an unconstrained account if strict $0 is required.
- The cloud web service continues to work with your laptop off, but new scan
  requests will queue without execution. **Do not publicly advertise scan
  availability until we add/test worker-presence gating and job recovery.**

## Stage A — Install patch and verify locally

Unzip files over the repository **on `deploy/render-demo` only**; do not
replace/remove existing working Docker Compose files or credentials.
Run `docker compose --env-file .env.docker ps` and verify local services remain
healthy. New cloud mode only activates with `PRIVACHECK_SERVE_FRONTEND=1`.
The GitHub Actions checks must also pass before any cloud resource is created.
This is a CI gate; deployment itself remains manual and approved.

The frontend build must use `VITE_API_BASE_URL=/api`. The hosted app serves
React at `/`, `/scans`, `/admin`, etc. API endpoints are `/api/auth/*`,
`/api/scans`, `/api/admin/*`, `/api/frameworks`. The only unprefixed auth route
needed by Google is `/auth/google/callback`. Render health check is `/healthz`.

## Stage B — Create free Render infrastructure (not before patch is tested)

From https://dashboard.render.com/ select New > Postgres > Free and set a
nonsecret project name, then New > Key Value > Free (same region), and set
`noeviction` policy. Create the web service from the `deploy/render-demo`
branch, specifying `Dockerfile.render` and Free plan (or apply `render.yaml`).
Keep auto-deploy disabled initially.

Set the web service environment variables in Render Dashboard, NOT in Git:

- `ENVIRONMENT=production`, `AUTH_COOKIE_SECURE=true`,
  `AUTH_COOKIE_SAMESITE=lax`, `PRIVACHECK_SERVE_FRONTEND=1`
- `DATABASE_URL`: Render **internal** PostgreSQL URI, converting its scheme
  from `postgresql://`/`postgres://` to `postgresql+psycopg://`.
- `BROKER_URL`: Render **internal** Key Value URI plus `/0`.
- `AUTH_RATE_LIMIT_REDIS_URL`: same **internal** Key Value URI plus `/1`.
- `AUTH_OAUTH_REDIS_URL`: same **internal** Key Value URI plus `/2`.
- `FRONTEND_ORIGIN`, `CORS_ORIGINS`: exact assigned
  `https://YOUR-ASSIGNED-NAME.onrender.com` address.
- `GOOGLE_REDIRECT_URI`: same hostname, `/auth/google/callback` suffix.
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`: confidential dedicated
  Google Cloud web client; callback registered verbatim with Google.
- `DB_POOL_SIZE=2`, `DB_MAX_OVERFLOW=1`.

**Important:** Free Render Postgres should be seeded using a fresh demo DB;
never point these variables at your local dev DB. Secret URLs must not be
included in Git commits, terminal screenshots, or chat messages.

## Stage C — Connect local workers to Render

On Render Postgres **Networking**, restrict external access to your
current public IPv4 `/32`. On Render Key Value **Networking**, enable
external access and allow the SAME IP. Key Value external links require TLS
and credentials. Render internal Key Value connections are normally `redis://`;
external connections are `rediss://`. On the workers, `BROKER_URL` MUST include
`?ssl_cert_reqs=required` as Celery uses Redis for both broker and backend.

Copy `deploy/render-workers.env.example` to repository-root
`.env.render-workers` and populate it with **external**, not internal,
connection URLs. Keep file local and Git-ignored. DB URL must have
`sslmode=require`. The workers must not use localhost database/queue URLs.

On your laptop (PowerShell, repo root):

```powershell
# Only after creating .env.render-workers and cloud resources:
docker compose -f deploy/worker-render-compose.yml config --quiet
# Prebuild the common workers image once:
docker compose -f deploy/worker-render-compose.yml build crawler-worker
# Run Alembic from laptop against remote Render Postgres:
docker compose -f deploy/worker-render-compose.yml run --rm --no-deps --entrypoint python crawler-worker -m alembic upgrade head
# Admit first user before Google sign-in (adjust only to an approved email):
docker compose -f deploy/worker-render-compose.yml run --rm --no-deps --entrypoint python crawler-worker -m backend.scripts.manage_allowlist email add YOUR_EMAIL
# After first Google sign-in to public app, bootstrap first admin:
docker compose -f deploy/worker-render-compose.yml run --rm --no-deps --entrypoint python crawler-worker -m backend.scripts.bootstrap_admin YOUR_EMAIL
# Start remote workers only; local development services are untouched:
docker compose -f deploy/worker-render-compose.yml up -d --no-build
```

Verify Celery connected to remote broker, worker registration, and full
end-to-end scan. Google sign-in test user must be configured in Google Auth
Platform's **Audience** panel if the OAuth app remains in Testing mode.

For the demo, keep laptop and Docker Desktop on. Before switching the
shared cloud URL live, rotate secrets exposed in older Git commits and
confirm role authorization, permissions, and scan output. Back up the free
Render DB using an encrypted private `pg_dump` before its expiration.

## Known blockers requiring additional work before open public scanning

- The existing URL guards are not a complete browser network egress boundary.
  Use controlled targets while demonstrating; isolate crawler network before
  accepting arbitrary user-submitted sites.
- There is no durable broker recovery on Render Free; a queue restart can
  orphan queued jobs. Add stale-job reconciliation before using with others.
- The API does not yet require workers to be online before queueing; don't
  claim new scans will always complete while the laptop is offline.
- This package has source/build checks but is NOT a validated end-to-end
  hosted deployment. Verify TLS, DB migration, Google login, worker jobs, and
  reports on the actual Render environment.

## References

- https://render.com/docs/free
- https://render.com/docs/postgresql-creating-connecting
- https://render.com/docs/key-value
- https://docs.celeryq.dev/en/v5.6.3/userguide/configuration.html
