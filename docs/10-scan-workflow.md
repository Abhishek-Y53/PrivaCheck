# Scan Workflow

## 1. Scan Lifecycle

User submits URL.

↓

API validates URL.

↓

API creates Scan record.

↓

API places scan job on queue.

↓

Worker receives job.

↓

Crawler begins.

↓

Website is analyzed.

↓

Observations are stored.

↓

Compliance checks execute.

↓

NLP analysis executes.

↓

Results are scored.

↓

Report is generated.

↓

Scan becomes COMPLETED.

## 2. Detailed Workflow

URL
→ Validation
→ SSRF protection
→ Scan creation
→ Queue
→ Orchestrator
→ Browser initialization
→ Homepage crawl
→ Relevant page discovery
→ DOM analysis
→ Network capture
→ Cookie capture
→ Storage capture
→ Header analysis
→ Accept Pass
→ Reset browser state
→ Reject Pass
→ State diff
→ Policy extraction
→ NLP analysis
→ Compliance rules
→ Result aggregation
→ Score
→ Report
→ COMPLETED

## 3. Two-Pass Workflow

### Pass 1: Accept State

1. Load page
2. Detect consent UI
3. Click Accept All
4. Record cookies
5. Record storage
6. Record network requests
7. Record relevant state

### Pass 2: Reject State

1. Clear browser state
2. Reload page
3. Click Reject All
4. Record cookies
5. Record storage
6. Record network requests
7. Record relevant state

### Diff

Compare:

- Cookies
- Storage
- Tracking requests
- Third-party requests

The compliance engine evaluates the differences.

## 4. Asynchronous Requirement

The API must not wait for the complete scan.

The API returns a scan identifier.

The frontend can subsequently request status/results.

Later versions may use:

- Server-Sent Events
- WebSockets

for live progress.