# Technology Stack

## 1. Recommended Stack

| Layer | Technology |
|---|---|
| Frontend | React |
| Frontend language | TypeScript |
| Frontend build tool | Vite |
| Backend | Python |
| API framework | FastAPI |
| Browser automation | Playwright |
| Browser | Chromium |
| Task queue | Celery |
| Message broker | Valkey |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Database migrations | Alembic |
| HTML parsing | BeautifulSoup + lxml |
| NLP | spaCy |
| Fuzzy matching | RapidFuzz |
| Readability | textstat |
| Semantic NLP | sentence-transformers |
| Containerization | Docker |
| Reverse proxy | Nginx |
| Testing | pytest |
| Frontend testing | Vitest + Playwright |
| Version control | Git + GitHub |

## 2. Alternatives

### Backend

Recommended:
FastAPI

Alternatives:
- Django REST Framework
- Flask
- Go + Gin
- Node.js + Fastify

### Browser Automation

Recommended:
Playwright

Alternatives:
- Selenium
- Puppeteer

### Database

Recommended:
PostgreSQL

Alternatives:
- MySQL
- MariaDB
- SQLite

SQLite is intended only for small development/testing scenarios.

### Task Queue

Recommended:
Celery + Valkey

Alternatives:
- RQ + Valkey
- Dramatiq + RabbitMQ
- Celery + RabbitMQ

### Frontend

Recommended:
React + TypeScript + Vite

Alternatives:
- Vue + TypeScript
- Svelte
- Next.js

### NLP

Initial:
- Regex
- RapidFuzz
- spaCy

Advanced:
- sentence-transformers

Large language models are not required for the initial implementation.
