# Architecture Decision Record

## ADR-001: Use FastAPI

### Decision

Use Python FastAPI as the backend API framework.

### Reason

The project is heavily Python-oriented because of:

- Playwright
- NLP
- Data processing
- Testing

FastAPI also provides strong API-schema support.

---

## ADR-002: Use Playwright

### Decision

Use Playwright for browser automation.

### Reason

The crawler requires:

- DOM interaction
- Network inspection
- Cookies
- Browser storage
- Consent interaction
- Dynamic-page support

A simple HTTP crawler is insufficient.

---

## ADR-003: Use PostgreSQL

### Decision

Use PostgreSQL as the primary database.

### Reason

The project contains structured relational entities and relationships.

---

## ADR-004: Use Asynchronous Workers

### Decision

Browser crawling must run asynchronously.

### Reason

Browser scans may take much longer than an HTTP request should remain open.

---

## ADR-005: Use Queue-Based Architecture

### Decision

Use a message queue between the API/orchestrator and workers.

### Reason

This allows:

- Asynchronous processing
- Retry
- Worker scaling
- Fault isolation
- Future distributed deployment

---

## ADR-006: Separate Crawler and Compliance Engine

### Decision

The crawler produces observations.
The compliance engine evaluates them.

### Reason

This makes compliance checks independently testable and extendable.

---

## ADR-007: Evidence-First Results

### Decision

Every compliance finding should contain supporting evidence.

### Reason

Results must be explainable and auditable.

---

## ADR-008: Avoid Immediate Full Microservices

### Decision

Use modular services/components initially rather than many independent deployments.

### Reason

The project should remain manageable while preserving future service boundaries.

---

## ADR-009: Avoid Paid Technologies

### Decision

Development must rely on free/open-source software.

### Reason

The project is being developed as a student project with a zero-software-cost constraint.

---

## ADR-010: Do Not Depend on LLMs Initially

### Decision

Use deterministic rules and lightweight NLP first.

### Reason

The majority of checks can be implemented without an LLM, reducing:

- Cost
- Complexity
- Nondeterminism
- Infrastructure requirements

Semantic models may be introduced later.

---

## ADR-011: Protect the Crawler as an Untrusted-URL Component

### Decision

The crawler must implement SSRF protection and resource limits.

### Reason

Users can submit arbitrary URLs, making the crawler a potential attack surface.