# Scan pipeline and report aggregation

## Added modules

- `backend/api/services/scan_pipeline.py`: allowlisted framework selection, request-model validation, DNS/public-destination validation before browser startup, crawler orchestration, declarative rule evaluation, safe manual-review outcomes for evaluators that the one-pass workflow cannot execute, and report assembly.
- `backend/reporting/report_builder.py`: consistent counters, overall status aggregation, deterministic severity-weighted risk score, and report evidence redaction.
- Tests live in `tests/api/test_scan_pipeline.py` and `tests/reporting/test_report_builder.py`.

This is an additive service layer. It intentionally does not replace the existing `backend/api/services/scan_service.py` or route response model without inspecting those current files. Wire the existing API service to delegate to `ScanPipelineService.scan(url, framework)` and then adapt the returned `ScanReport` to the existing public response model.

## Security behavior

- The whole scan has a configurable wall-clock timeout (180 seconds by default).
- The framework maps to a fixed application-owned YAML path. A request cannot supply a filesystem path or use path traversal to select rules.
- `ScanRequest` performs syntax/URL policy checks. The pipeline separately awaits DNS/public-address validation before starting the crawler. The crawler itself should repeat this validation immediately before browser navigation.
- Do not expose this service publicly until the browser worker has external egress restrictions. Application checks alone cannot eliminate DNS rebinding/time-of-check-to-time-of-use races.
- Report evidence is copied and redacted: cookie/storage values, credential headers, obvious token fields, and query values in URLs are removed from the serialized report. Original in-memory observations are not mutated, so rules must be evaluated before report sanitization.
- Unexpected per-rule evaluator errors are logged internally and rendered as `MANUAL_REVIEW`; raw exception details are not inserted into the report.

## Report status and risk policy

- Any observed `FAIL` makes the aggregate report `FAIL`.
- An incomplete crawler run, empty check set, all-not-applicable check set, or unavailable/failed evaluator requires `MANUAL_REVIEW` unless a concrete `FAIL` already exists.
- If no `FAIL` or `MANUAL_REVIEW` exists, any `WARNING` produces `WARNING`; otherwise applicable checks that all `PASS` produce `PASS`.
- `failed_checks` counts only `FAIL`. Warnings and manual reviews are retained in `metadata.result_counts`.
- Risk score is the severity-weighted mean of status factors: `FAIL=1.0`, `WARNING=0.5`, `MANUAL_REVIEW=0.25`, `PASS=0.0`; non-applicable checks are excluded. Severity weights are CRITICAL 5, HIGH 4, MEDIUM 3, LOW 2, INFO 1. The 0–100 score is a project heuristic, not a probability, legal certification, or calibrated confidence score.

## Framework support

Only `gdpr` is registered by default because `rules/gdpr/rules.yaml` is the confirmed configured rule set in this source snapshot. Add another framework only by registering a fixed path in `DEFAULT_FRAMEWORK_RULE_FILES` after its YAML rules and tests exist. Do not accept a rule path supplied by API callers.

## Test

```powershell
python -m pytest tests/reporting tests/api -q
```

To verify the integrated application, run the existing crawler/security/rule-engine suites in the working repository. Live-browser integration must also be checked there because this source archive omits some newer crawler modules.

## Connect it to the existing API

The current uploaded repository snapshot did not include the later local
`backend/api/services/scan_service.py` or `backend/api/routes/scans.py`, so this
patch intentionally does not overwrite or guess at their response contract.
After copying these additive files, the existing API service can delegate to
this pipeline. If its request model uses `website` (as an older API contract
may), pass `request.website`; if it uses the new security `ScanRequest`, pass
`request.url`:

```python
report = await ScanPipelineService().scan(
    url=request.url,          # or request.website in the older request schema
    framework=request.framework,
)
```

If the API must preserve an existing `ScanResponse` shape, map the report fields
at that boundary rather than changing the public API by accident. The response
adapter should pass the sanitized `report.issues`, not raw crawler observations.
Translate `UnsafeScanTargetError` into a controlled 422 response and
`UnsupportedFrameworkError` into a controlled 422 response. Do not return raw
tracebacks or exception strings to clients.
