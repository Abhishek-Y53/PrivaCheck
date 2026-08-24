                         ┌─────────────────────────┐
                         │        FRONTEND         │
                         │      React + Vite       │
                         └────────────┬────────────┘
                                      │
                                      │ HTTPS / REST
                                      ▼
                         ┌─────────────────────────┐
                         │       API SERVICE       │
                         │        FastAPI          │
                         │                         │
                         │ Auth                    │
                         │ URL validation          │
                         │ Scan creation           │
                         │ Scan status             │
                         │ Report API              │
                         └────────────┬────────────┘
                                      │
                                      │ enqueue jobs
                                      ▼
                         ┌─────────────────────────┐
                         │      MESSAGE BROKER      │
                         │       Valkey / Redis    │
                         │                         │
                         │ scan jobs               │
                         │ crawl jobs              │
                         │ analysis jobs           │
                         └───────┬────────┬────────┘
                                 │        │
                    ┌────────────┘        └─────────────┐
                    ▼                                   ▼
       ┌────────────────────────┐          ┌────────────────────────┐
       │    CRAWLER WORKER      │          │     ANALYSIS WORKER    │
       │                        │          │                        │
       │ Playwright             │          │ DOM Rules              │
       │ Chromium               │          │ Network Rules          │
       │ Network interception   │          │ Cookie Rules            │
       │ DOM extraction         │          │ Security Header Rules   │
       │ Cookie/storage capture │          │ NLP / Policy Rules      │
       │ Two-pass testing       │          │ Scoring                 │
       └───────────┬────────────┘          └───────────┬────────────┘
                   │                                   │
                   │ observations                      │ results
                   └──────────────┬────────────────────┘
                                  ▼
                       ┌─────────────────────────┐
                       │       PostgreSQL        │
                       │                         │
                       │ Scan                    │
                       │ Page                    │
                       │ NetworkRequest          │
                       │ Cookie                  │
                       │ StorageSnapshot         │
                       │ Policy                  │
                       │ CheckResult             │
                       │ Report                  │
                       └─────────────────────────┘

                                  │
                                  ▼
                       ┌─────────────────────────┐
                       │     REPORT SERVICE      │
                       │                         │
                       │ Score                   │
                       │ Findings                │
                       │ Evidence                │
                       │ Recommendations         │
                       │ JSON / PDF later        │
                       └─────────────────────────┘