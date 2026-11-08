# PrivaCheck M9 — Docker Compose local environment

This package runs the complete PrivaCheck application locally with Docker Compose:

- PostgreSQL 17 (persistent volume)
- Valkey 8 (persistent volume)
- Alembic migration job
- FastAPI API
- Independent Playwright crawler worker
- Independent compliance worker
- React production build served by Nginx

The Python backend image installs Chromium and its Linux dependencies. It runs as an unprivileged `privacheck` user. The crawler worker has a dedicated 1 GiB shared-memory allocation and a single worker process to limit browser memory pressure.

## 1. Prerequisites

- Docker Desktop running with the Linux container engine enabled
- Docker Compose plugin
- At least 4 GB RAM available to Docker Desktop; 6–8 GB is preferable because Chromium is memory-intensive

## 2. Create the local Compose environment file

From the repository root in PowerShell:

```powershell
Copy-Item .env.docker.example .env.docker

# Keep the local secrets file out of Git history.
Add-Content .gitignore "`n.env.docker`n.env.docker.*"
```

The supplied values are **local-development-only** and preserve compatibility with the previous Compose PostgreSQL volume (`postgres` / `postgres`). Do not expose these ports to a public network or reuse these credentials in production.

If you are starting with a fresh Compose volume and want a stronger local database password, generate a URL-safe 32-byte hexadecimal password:

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

Replace `POSTGRES_PASSWORD` in `.env.docker` with that value. If an existing PostgreSQL volume was initialized using a different password, changing this environment variable does not alter the existing database role password. Keep the original value or change the database role password explicitly before changing the Compose environment.

## 3. Validate Compose configuration

```powershell
docker compose --env-file .env.docker config --quiet
```

If the command returns an error, do not start the stack; inspect the reported YAML or interpolation error first.

## 4. Build and start all services

```powershell
docker compose --env-file .env.docker up --build -d
```

The first build downloads Python/Node dependencies and the Playwright Chromium browser, so it requires internet access and may take longer than subsequent starts.

Compose starts PostgreSQL and Valkey first, waits for their health checks, runs `alembic upgrade head`, and then starts the API and workers. The frontend starts after the API health check passes.

## 5. Check service status

```powershell
docker compose --env-file .env.docker ps
```

Expected steady state:

- `postgres`: healthy
- `valkey`: healthy
- `migrate`: exited (0)
- `api`: healthy
- `crawler-worker`: healthy
- `compliance-worker`: healthy
- `frontend`: healthy

The migration container being `Exited (0)` is expected; it is a one-shot job, not a continuously running server.

Open the application at:

- Frontend: <http://localhost:5173>
- API health: <http://localhost:8000/>
- API docs: <http://localhost:8000/docs>

Use **localhost consistently** in the browser. The configured frontend origin, API URL, CSRF origin validation, and local non-Secure SameSite=Lax cookies are configured for `http://localhost`. Do not mix `localhost` and `127.0.0.1` while testing login/session cookies.

## 6. Inspect logs

```powershell
docker compose --env-file .env.docker logs --tail=150 migrate api crawler-worker compliance-worker frontend
```

Follow worker logs while submitting a scan:

```powershell
docker compose --env-file .env.docker logs -f crawler-worker compliance-worker
```

Check the Celery workers from the host (requires the local Python environment with dependencies installed):

```powershell
python -m celery -A backend.services.crawler_service.celery_app:crawler_celery_app inspect ping
python -m celery -A backend.services.compliance_service.celery_app:compliance_celery_app inspect ping
```

Or inspect them from their containers:

```powershell
docker compose --env-file .env.docker exec crawler-worker python -m celery -A backend.services.crawler_service.celery_app:crawler_celery_app inspect ping

docker compose --env-file .env.docker exec compliance-worker python -m celery -A backend.services.compliance_service.celery_app:compliance_celery_app inspect ping
```

## 7. Common operations

Restart only the workers:

```powershell
docker compose --env-file .env.docker restart crawler-worker compliance-worker
```

Rebuild after changing backend dependencies or Python source:

```powershell
docker compose --env-file .env.docker up --build -d api crawler-worker compliance-worker
```

Rebuild the frontend after changing React/TypeScript source:

```powershell
docker compose --env-file .env.docker up --build -d frontend
```

Stop containers but preserve database and Valkey data:

```powershell
docker compose --env-file .env.docker down
```

**Do not use `docker compose down -v` unless you intentionally want to delete the PostgreSQL and Valkey volumes.** That command permanently removes the local persistent data stored in those volumes.

## 8. Security and deployment boundary

This Compose file is for local development, not a public production deployment:

- Published ports bind to `127.0.0.1` only.
- Local HTTP requires `AUTH_COOKIE_SECURE=false`; production must use HTTPS and `AUTH_COOKIE_SECURE=true`.
- PostgreSQL/Valkey use local-development settings and are not configured for public exposure.
- No production secrets are baked into either image. `.env.docker` is a local file and must not be committed.
- The API and workers run as a non-root user. PostgreSQL and Valkey use their official images.
- The crawler launches Chromium against user-submitted public URLs. Keep the API private to your machine during local development; production network-egress controls and stronger isolation belong in M10 hardening.

For remote deployment, use managed or properly secured PostgreSQL/Valkey, HTTPS, strong secrets, a restricted CORS origin, secure cookies, appropriate resource limits, and network/egress controls. Do not simply publish these local Compose ports to the internet.

## 9. Troubleshooting

### Migration job failed

```powershell
docker compose --env-file .env.docker logs migrate
```

Fix the reported error, then rerun:

```powershell
docker compose --env-file .env.docker run --rm migrate
```

Then start/recreate dependent services:

```powershell
docker compose --env-file .env.docker up -d api crawler-worker compliance-worker frontend
```

### Worker is unhealthy or scans remain queued

```powershell
docker compose --env-file .env.docker logs --tail=200 crawler-worker compliance-worker
```

```powershell
docker compose --env-file .env.docker restart crawler-worker compliance-worker
```

Wait for both worker health checks to become healthy before submitting another scan.

### Database credentials do not work

If you reused an existing `postgres_data` volume, the actual PostgreSQL role/password are those established when that volume was first initialized. The `POSTGRES_*` variables are only used by the official image on first initialization. Updating `.env.docker` alone does not rotate an existing role password.

### Chromium/browser launch fails

Check crawler logs and verify the backend image was rebuilt after dependency changes:

```powershell
docker compose --env-file .env.docker build --no-cache crawler-worker
```

Then:

```powershell
docker compose --env-file .env.docker up -d crawler-worker
```
