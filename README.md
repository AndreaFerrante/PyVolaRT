# GEX Dashboard — SPX Gamma Exposure

Semi-real-time Gamma Exposure (GEX) dashboard for SPX index options. Two
services, one versioned contract:

- **`backend/`** — Python 3.12 / FastAPI. Acquires market data (IBKR via
  `ib_async`, or a built-in simulator), computes GEX + flip curve, persists
  history, and serves REST + a WebSocket push feed.
- **`frontend/`** — React 18 / TypeScript (strict) / Vite. shadcn/ui + SCSS
  modules, TanStack Query data layer, Recharts. Renders the metrics strip and
  the diverging Strike Profile chart.
- **`tasks/`** — the engineering record: `PLAN.md` (decisions D1–D8, milestones
  M0–M9), `ARCHITECTURE.md` (contract + component design), `TODO.md`.

```
gex-dashboard/
├── backend/      FastAPI service  → see backend/README.md for full detail
├── frontend/     React dashboard  → see frontend/README.md for full detail
├── tasks/        PLAN.md · ARCHITECTURE.md · TODO.md
└── README.md     this file
```

## Prerequisites

Python **3.12+** and Node **18+** (built and verified on Python 3.12 / Node 22).
No broker, no database server, no other infra needed for the default mode: the
backend ships with a **simulated provider** and SQLite, so the full stack runs
out of the box.

## Run it (two terminals)

**Terminal 1 — backend (start this first):**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app                # http://127.0.0.1:8000
```

Sanity check it's up:

```bash
curl http://127.0.0.1:8000/healthz              # {"status":"ok"}
curl http://127.0.0.1:8000/api/v1/gex/current   # full GexSnapshot JSON
```

Interactive API docs: http://127.0.0.1:8000/docs

**Terminal 2 — frontend:**

```bash
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

Open http://localhost:5173 — you should see the metrics strip populate within a
couple of seconds and the Strike Profile chart ticking as the simulator walks
spot around.

If the backend is not on `127.0.0.1:8000`, point the frontend at it:

```bash
cp .env.example .env    # edit VITE_API_BASE, then restart `npm run dev`
```

## How the communication works

The contract is the set of Pydantic models in `backend/app/core/models/`
(`GexSnapshot`, `GexLevels`, `FlipCurve`, `DataQuality`, `WsEnvelope`, …),
mirrored field-for-field by `frontend/src/types/api.ts` and served under
`/api/v1`.

1. **Bootstrap (REST).** On load the frontend fetches
   `GET /api/v1/gex/current` through TanStack Query, so the dashboard renders
   from the first response.
2. **Live feed (WebSocket).** Simultaneously it opens
   `WS /api/v1/ws/stream` (URL derived from `VITE_API_BASE`, `http→ws`). The
   server immediately replays the latest snapshot + quality (bootstrap
   envelopes), then pushes every recompute: `gex_snapshot`, `flip_curve`,
   `quality` changes, and ~10 s `heartbeat`s. Each envelope carries a schema
   version `v` and a monotonic `seq` for gap/restart detection. The frontend
   writes these messages **into the same TanStack Query cache** the REST
   bootstrap filled, so components don't know or care which path a value
   arrived by.
3. **History (REST).** The Net GEX sparkline queries
   `GET /api/v1/gex/history?limit=…` (SQLite by default, Postgres via one DSN
   env var) on a 15 s TanStack Query refresh.
4. **Fallbacks.** If the socket drops, the frontend auto-reconnects every 2 s
   and the low-frequency REST polling on `gex/current` keeps data flowing in
   the meantime. CORS is already enabled on the backend (`GEX_CORS_ORIGINS`,
   default `*`), so the Vite dev server needs no proxy.

A third consumer (e.g. a trading service) uses the same surface:
`GET /api/v1/gex/levels` for the fast regime/walls path, or the same WebSocket.

## Switching to live IBKR data

The default `GEX_PROVIDER=simulated` requires nothing. The live path is one
env var — `GEX_PROVIDER=ibkr` — plus `pip install ib_async` and a running
IB Gateway/TWS (`GEX_IBKR_HOST/PORT/CLIENT_ID`). **Caveat:** per
`tasks/PLAN.md`, milestone M2 (the live feasibility spike validating OI tick
101 for index options and snapshot-greeks reliability) has not been run yet;
the IBKR provider is written to spec but unverified against a live feed. The
simulator is the supported mode until M2 passes. Run a **single** uvicorn
worker either way — market-data lines belong to one IBKR session.

## Verifying the code

```bash
# backend: boots the app on the simulator, exercises every REST endpoint + WS
cd backend && pytest -q

# frontend: strict typecheck / production build
cd frontend && npm run typecheck
cd frontend && npm run build
```

## Configuration quick reference

Backend env vars use the `GEX_` prefix (see `backend/.env.example`): provider,
database URL, underlying, strike window, recompute cadence, CORS. Frontend has
a single variable, `VITE_API_BASE` (see `frontend/.env.example`).
