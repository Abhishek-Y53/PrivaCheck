# M0 decisions captured in the frontend starter

1. Frontend: React + TypeScript + Vite.
2. UI styling: authored CSS with design tokens; no paid components or UI service.
3. Initial pages: Overview, New scan, Scan history, Scan report.
4. Initial enabled framework: GDPR only, matching the currently registered backend rule set.
5. Demo account: no authentication screen in M1. User/account authentication is a later phase before public multi-user exposure.
6. Demo data: explicitly labelled and enabled by default. The simulated scan is not a live crawler execution.
7. Target API: asynchronous REST API with distinct lifecycle and compliance statuses.
8. Backend deployment: intentionally undecided until the deployment phase.
