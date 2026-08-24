# Development Roadmap

## Phase 1 — Project Foundation

- Repository structure
- Docker
- PostgreSQL
- FastAPI
- React
- Basic API
- Basic frontend
- Scan model

## Phase 2 — Browser Infrastructure

- Playwright
- Chromium
- Browser manager
- Page loader
- URL validation
- SSRF protection
- Resource limits

## Phase 3 — Observation System

Implement:

- DOM collector
- Network collector
- Cookie collector
- Storage collector
- Header collector
- Link extractor

## Phase 4 — Compliance Engine

Implement common check interface.

Then implement Group A checks.

## Phase 5 — Network Checks

Implement Group B checks.

## Phase 6 — Stateful Consent Testing

Implement:

- Accept pass
- Browser-state reset
- Reject pass
- Diff engine

## Phase 7 — Policy/NLP

Implement Group C:

- Policy discovery
- Text extraction
- Keyword matching
- NLP
- Readability
- Language analysis

## Phase 8 — Queue and Workers

Introduce:

- Celery
- Valkey
- Worker processes
- Scan orchestration

## Phase 9 — Reports

Implement:

- Scoring
- Evidence
- Findings
- Recommendations
- Report generation

## Phase 10 — Frontend

Implement:

- Scan form
- Scan progress
- Results dashboard
- Check details
- Evidence viewer
- Report page

## Phase 11 — Testing

- Unit tests
- Integration tests
- Crawler tests
- Rule tests
- NLP tests
- API tests
- Security tests

## Phase 12 — Scaling

Only after the core system is stable:

- Multiple crawler workers
- Multiple NLP workers
- Artifact storage
- Caching
- Rate limiting improvements
- Production deployment