# System Architecture

## 1. Architectural Style

The system uses a modular, event-driven architecture with independently scalable workers.

The architecture is intentionally designed to support future decomposition into true microservices without requiring a complete redesign.

We will not initially create a large number of independent services.

Instead, the project will use clear module/service boundaries and asynchronous workers.

## 2. High-Level Architecture

Frontend
→ API Service
→ Message Broker
→ Worker Services
→ Database
→ Report Service
→ Frontend

## 3. Components

### Frontend

Responsible for:

- URL submission
- Scan initiation
- Scan status
- Result visualization
- Compliance score
- Findings
- Evidence
- Recommendations
- Reports

Technology:

React + TypeScript + Vite

### API Service

Responsible for:

- API endpoints
- URL validation
- Scan creation
- Scan status
- Result retrieval
- Report retrieval
- Authentication in future versions

Technology:

FastAPI

The API must not perform browser crawling directly.

### Scan Orchestrator

Responsible for:

- Managing scan lifecycle
- Creating crawler jobs
- Coordinating analysis
- Triggering report generation
- Updating scan status
- Handling failures and timeouts

### Message Broker

Responsible for:

- Asynchronous task delivery
- Queue management
- Worker coordination

Technology:

Valkey

### Crawler Workers

Responsible for:

- Browser execution
- DOM extraction
- Network interception
- Cookie capture
- Browser-storage capture
- Header inspection
- Link discovery
- Policy-page discovery
- Consent interaction
- Two-pass testing

Technology:

Python + Playwright + Chromium

### Compliance Engine

Responsible for evaluating collected observations against compliance rules.

The compliance engine must not control browser execution.

### NLP Engine

Responsible for:

- Privacy-policy text processing
- Keyword matching
- Entity extraction
- Semantic matching
- Readability analysis
- Language analysis

### Report Engine

Responsible for:

- Compliance score
- Check summaries
- Evidence
- Recommendations
- Final report generation

### Database

Responsible for persistent structured data.

Technology:

PostgreSQL

## 4. Architectural Principle

Crawler != Compliance Rule

The crawler generates observations.

The compliance engine evaluates observations.

## 5. Scaling Model

Different components should be independently scalable.

Example:

API:
2 instances

Crawler:
20 workers

NLP:
5 workers

Database:
1 primary

Queue:
1 or clustered deployment depending on scale

The architecture therefore supports horizontal scaling without changing the core application design.