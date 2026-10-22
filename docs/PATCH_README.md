# PrivaCheck security patch: URL validation and browser egress guard

## Apply

From the PrivaCheck repository root, extract this ZIP with **merge/overwrite** enabled so the paths in the archive land under the existing `backend/`, `tests/`, and `docs/` directories. Review the diffs before committing. The patch preserves the current consent-phase-aware `SinglePassRunner` logic; it does not replace the crawler/rule-engine architecture.

Included source files:

* `backend/security/url\_validation.py` — strict URL parser, DNS public-address validator, browser HTTP/WebSocket guard and scan budgets.
* `backend/schemas/scan\_request.py` — Pydantic request contract for scan endpoints.
* `backend/crawler/orchestrator.py` — guards the existing direct-navigation + page-traversal flow and revalidates before TLS evidence collection.
* `backend/crawler/pass\_runner.py` — preserves before/after-consent evidence tagging while enforcing the URL/network guard before navigation.
* `backend/crawler/two\_pass.py` — validates URL syntax before allocating pass contexts and blocks service workers in fresh contexts.
* `backend/crawler/browser.py` — blocks service workers in the regular crawler context.
* `tests/security/` — deterministic URL, DNS-policy, request-guard and runner integration tests.

## Run tests

```powershell
python -m pytest tests/security -q
python -m pytest tests -q
```

The pre-existing `tests/crawler/test\_pass\_runner.py` uses fake browser contexts. Update its test setup to mock `validate\_public\_http\_url` and `PublicNetworkGuard.install()` rather than performing real DNS checks or using a context without routing APIs. The fake browser in `tests/crawler/test\_two\_pass.py` should accept `new\_context(\*\*kwargs)` and assert `service\_workers == "block"`. Do not add test-only bypasses to production code.

## Do not treat this patch as production SSRF isolation

The application validates all DNS answers and checks browser HTTP(S)/WebSocket requests, but Chromium and the TLS collector can resolve the hostname again when connecting. Playwright routing also cannot constrain every possible OS/browser networking mechanism. Before exposing a scan API, isolate the crawler in a dedicated unprivileged container/worker with outbound network policy or a controlled egress proxy that blocks private/internal/metadata networks and pins the actual destination.

The current repository's Docker Compose configuration also publishes PostgreSQL and Valkey ports without binding them to loopback, and uses a default PostgreSQL password. This patch deliberately does not alter those connection settings; harden them as a separate coordinated change before deployment. The existing collectors can also capture cookie values, storage values and request headers, so evidence redaction/access control remains a required follow-up.

