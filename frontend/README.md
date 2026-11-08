# PrivaCheck Frontend (M1 starter)

React + TypeScript + Vite frontend for the PrivaCheck compliance assessment platform.

## Current scope

- Overview dashboard
- New scan form
- Scan history with search and lifecycle filter
- Scan detail/report page with result filters and expandable evidence
- Mock scan lifecycle so the screens can be developed before the asynchronous backend exists
- API client and TypeScript contracts for the planned asynchronous API

## Important: demo mode

The default `.env.example` uses `VITE_USE_MOCK_DATA=true`. In this mode all scans/reports are sample data stored in browser localStorage. A newly submitted scan follows a simulated lifecycle. It does **not** launch the Python crawler.

Keep mock mode enabled until the asynchronous API contract is implemented and tested.

## Requirements

- Node.js 20.19+ (or 22.12+)
- npm

Check versions:

```powershell
node --version
npm --version
```

## Run locally

From the `frontend` directory:

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://127.0.0.1:5173`).

Production build check:

```powershell
npm run build
```

## API mode (not wired to the existing synchronous endpoint yet)

The target API is documented in `docs/FRONTEND_API_CONTRACT.md`. When the backend implements that contract:

1. Set `VITE_USE_MOCK_DATA=false`.
2. Set `VITE_API_BASE_URL` to the backend API base URL.
3. Rebuild/restart the frontend.

The current backend's synchronous `POST /scans` response is not the target contract. Do not switch off mock mode until the asynchronous endpoints are available.
