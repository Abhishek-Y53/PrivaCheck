# PrivaCheck Frontend ↔ Backend API Contract (M0)

Version: 0.1 draft

This is the target contract for the asynchronous application. It is intentionally not a description of the existing synchronous `POST /scans` endpoint.

## Design decision: two kinds of status

Do not overload one status field for both worker execution and compliance outcome.

- `lifecycle_status`: `QUEUED | RUNNING | COMPLETED | FAILED`
- `overall_status`: `PASS | FAIL | WARNING | MANUAL_REVIEW`

`NOT_APPLICABLE` is a per-check result and is not an aggregate outcome.

## 1. List available frameworks

`GET /api/v1/frameworks`

Response:

```json
[
  {
    "id": "gdpr",
    "name": "GDPR",
    "description": "Technical website checks mapped to the configured GDPR rule set.",
    "enabled": true
  }
]
```

Only frameworks with validated, registered rule files should be returned as enabled.

## 2. Create scan

`POST /api/v1/scans`

Request:

```json
{
  "website": "https://www.example.com/",
  "framework": "gdpr"
}
```

Response: HTTP `202 Accepted`

```json
{
  "scan_id": "uuid",
  "website": "https://www.example.com/",
  "framework": "gdpr",
  "lifecycle_status": "QUEUED",
  "created_at": "2026-11-02T10:00:00Z"
}
```

The API must validate URL syntax/policy and framework allowlist, create a durable scan row, enqueue the task, and return. A response must not claim a scan was queued if enqueueing failed; the scan should be marked failed or rolled back safely.

## 3. List scan history

`GET /api/v1/scans?page=1&page_size=20`

Response:

```json
{
  "items": [
    {
      "scan_id": "uuid",
      "website": "https://www.example.com/",
      "framework": "gdpr",
      "lifecycle_status": "COMPLETED",
      "overall_status": "WARNING",
      "created_at": "2026-11-02T10:00:00Z",
      "started_at": "2026-11-02T10:00:01Z",
      "completed_at": "2026-11-02T10:00:18Z",
      "duration_seconds": 17.0,
      "total_checks": 42,
      "passed_checks": 20,
      "failed_checks": 0,
      "warning_checks": 4,
      "manual_review_checks": 3,
      "not_applicable_checks": 15,
      "observation_count": 1200,
      "risk_score": 18.2
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

## 4. Get scan lifecycle/status

`GET /api/v1/scans/{scan_id}`

Response while queued/running:

```json
{
  "scan_id": "uuid",
  "website": "https://www.example.com/",
  "framework": "gdpr",
  "lifecycle_status": "RUNNING",
  "created_at": "2026-11-02T10:00:00Z",
  "started_at": "2026-11-02T10:00:01Z",
  "completed_at": null,
  "duration_seconds": null,
  "error": null
}
```

When completed, include aggregate status and counters or let the frontend load the report endpoint.

## 5. Get assessment report

`GET /api/v1/scans/{scan_id}/report`

Response:

```json
{
  "scan_id": "uuid",
  "website": "https://www.example.com/",
  "framework": "gdpr",
  "overall_status": "WARNING",
  "total_checks": 42,
  "passed_checks": 20,
  "failed_checks": 0,
  "warning_checks": 4,
  "manual_review_checks": 3,
  "not_applicable_checks": 15,
  "observation_count": 1200,
  "duration_seconds": 17.0,
  "risk_score": 18.2,
  "risk_score_interpretation": "Heuristic score; not a probability or legal determination.",
  "created_at": "2026-11-02T10:00:00Z",
  "metadata": {},
  "results": [
    {
      "check_id": "GDPR-024",
      "name": "HTTPS with valid TLS certificate",
      "status": "PASS",
      "severity": "HIGH",
      "confidence": 1.0,
      "explanation": "Certificate verification succeeded.",
      "recommendation": null,
      "evidence": [
        {
          "category": "tls_certificate",
          "source_url": "https://www.example.com/",
          "timestamp": 1793613600.0,
          "data": {"protocol": "https", "verified": true}
        }
      ]
    }
  ]
}
```

Evidence returned by the API must already be sanitized. Never return raw cookie values, authorization headers, session tokens, or sensitive query parameters.

## 6. Health endpoints

- `GET /health/live`: process is alive.
- `GET /health/ready`: API can reach required dependencies (database, and broker if the endpoint's readiness policy requires it).

## Error conventions

- `400`: invalid request shape/business validation.
- `401/403`: authentication/authorization when enabled.
- `404`: scan or framework not found.
- `409`: invalid lifecycle operation/conflict.
- `422`: prohibited or invalid target URL / unsupported framework.
- `429`: rate or scan quota exceeded.
- `503`: required dependency unavailable / queue unavailable.

## Persistence and lifecycle rules

- PostgreSQL is the source of truth for scan lifecycle, report summary, results, and selected sanitized evidence.
- Valkey is a broker/temporary coordination layer, not permanent report storage.
- Create the scan database row before dispatching work.
- Worker updates `QUEUED -> RUNNING -> COMPLETED|FAILED`.
- A completed scan can have `overall_status=FAIL`; this is a compliance result, not an execution failure.
- Only the owner of a scan may read it once user authentication/ownership is introduced.
- A periodic reconciliation task should detect jobs left `RUNNING` after a worker crash and mark/requeue them under a defined retry policy.
