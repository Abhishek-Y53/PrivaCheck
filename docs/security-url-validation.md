# PrivaCheck URL and outbound-network hardening

## What this change covers

- `backend/security/url_validation.py` implements strict URL syntax checks, an HTTP/HTTPS scheme allow-list, canonical host handling, standard-port-only policy (HTTP 80 / HTTPS 443), rejection of credentials and ambiguous numeric hosts, and checks against loopback/private/link-local/reserved destination IPs.
- `validate_public_http_url()` resolves a hostname and rejects it if any returned IPv4/IPv6 address is not globally routable. Mixed public/private answers are rejected.
- `PublicNetworkGuard` applies the policy to Playwright HTTP(S) requests (including redirects, frames, scripts and subresources) and WebSocket destinations. It fails closed and applies per-scan request and distinct-host budgets.
- Browser contexts set `service_workers="block"` because Playwright request routing does not cover requests intercepted by service workers.
- `backend/schemas/scan_request.py` adds a Pydantic request model for use at future/current scan API boundaries. It performs syntax/policy validation; it does not replace the asynchronous DNS check before network access.
- The current normal crawler orchestrator validates before launching the browser, adds the request guard before navigation, revalidates before TLS evidence collection, and avoids exposing raw unexpected exception text to callers.
- The consent-aware `SinglePassRunner` retains its before/after-consent observation phase behavior while adding the same guard.

## Use at API boundaries

A scan endpoint should accept `ScanRequest`, not an unvalidated free-form string, and pass `request.url` to the scan service/orchestrator. The orchestration path must continue to perform the asynchronous DNS validation before network access; the Pydantic model alone is not enough.

## Test execution

Run from the repository root:

```powershell
python -m pytest tests/security -q
```

Security tests use deterministic/mock DNS answers and do not contact internal or external targets. Existing unit tests that use fake browser contexts must mock `validate_public_http_url` and `PublicNetworkGuard.install()` so they do not perform real DNS resolution; they must not disable the guard in production code. Tests using a fake browser's `new_context()` must accept the `service_workers="block"` keyword.

## Deployment requirement: application validation is not enough

**Do not expose a scan API publicly based only on this Python layer.** Chromium performs its own DNS resolution after validation, so a DNS rebinding/time-of-check-to-time-of-use race cannot be eliminated by a preflight DNS lookup. The TLS collector also makes a separate outbound connection. A malicious page may use networking mechanisms that are not covered by Playwright HTTP route handling.

Before deployment, run the crawler in a dedicated, unprivileged worker/container and enforce outbound egress restrictions outside the process. Deny loopback, RFC1918/private IPv4, IPv6 loopback/unique-local/link-local, link-local and cloud metadata destinations; do not allow the worker to connect to PostgreSQL, Valkey, the host gateway, orchestration APIs, or other internal services. Prefer a controlled egress proxy that resolves and pins the actual connection destination. Also restrict unnecessary UDP/QUIC/WebRTC egress. The policy needs to account for your cloud/VPC/Kubernetes service ranges, not just the standard private ranges.

## Remaining security work before production

- Add API authentication/authorization, rate limits, queue/concurrency limits, and scan time/page limits before exposing endpoints.
- Redact cookie values, authorization/cookie headers, sensitive query parameters, and storage values from persisted evidence and logs. Current collectors can capture sensitive values, so scan reports must not be publicly readable by default.
- Harden the existing local Docker Compose credentials and port bindings before using them outside a local development machine.
- Review the TLS collector to connect only to a previously validated destination (or route it through the egress proxy); DNS revalidation alone still has a race.
