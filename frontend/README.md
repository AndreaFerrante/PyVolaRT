# GEX Dashboard — Frontend

React + TypeScript dashboard for the GEX backend. Renders the eight-metric strip
and the diverging Strike Profile chart from the reference design, fed live over
WebSocket with REST fallback, and pulls Net GEX history through TanStack Query.

Stack: **React 18 + TypeScript** (strict), **Vite**, **shadcn/ui** (Radix +
Tailwind v3) for primitives, **SCSS modules** for dashboard styling,
**TanStack Query** for data fetching/cache, **Recharts** for charts.

## Quick start

```bash
cd frontend
npm install
cp .env.example .env          # set VITE_API_BASE if backend isn't on :8000
npm run dev                   # http://localhost:5173
```

The backend must be running (`uvicorn app.main:app` in ../backend). CORS is
already enabled there, so the Vite dev server on a different origin works without
a proxy.

```bash
npm run build      # tsc --noEmit && vite build  (type-checks, then bundles)
npm run typecheck  # tsc --noEmit only
npm run preview     # serve the production build
```

## Configuration

`VITE_API_BASE` — base URL of the FastAPI backend (default
`http://127.0.0.1:8000`). The WebSocket URL is derived from it
(`http`→`ws`, `https`→`wss`).

## How data flows

- `useGexStream` opens `/api/v1/ws/stream`, parses each `WsEnvelope`, and writes
  snapshots / flip curves / quality straight into the **TanStack Query cache**.
- Components read through `useCurrentGex()` / `useFlipCurve()`, so they see the
  same cache whether the value arrived via the REST bootstrap or a live push.
- REST polling on those queries is a low-frequency **safety net** for when the
  socket is down; the socket auto-reconnects with a fixed backoff.
- `useGexHistory()` calls `/api/v1/gex/history` and powers the Net GEX sparkline.

## Layout (matches the mockup)

- **MetricsStrip** — 8 cards: Spot, Net GEX (+ratio), Call GEX (+OI), Put GEX
  (+OI), Total GEX (+OI), Call Wall (+%), Put Wall (+%), Zero Gamma. Responsive
  4→2 columns. Net GEX and walls are sign/role-colored; "N/A" when null.
- **NetGexSparkline** — compact Net GEX trend from history.
- **StrikeProfile** — diverging bar chart: green call gamma up, red put gamma
  down (shared stack, `stackOffset="sign"`), dashed Spot reference line on a
  numeric strike axis, white-outlined wall bars, and an All/Near scope toggle
  (Near = the N strikes closest to spot).

## Types

`src/types/api.ts` mirrors the backend Pydantic models field-for-field and was
verified against the live JSON. In production these should be **generated** from
the backend's OpenAPI export (e.g. `openapi-typescript`) so any contract drift
fails the build.

## Layout of the code

```
src/
  api/          typed fetch client + endpoint wrappers
  hooks/        TanStack Query hooks + the WebSocket→cache hook
  types/        API contract types (mirror of backend models)
  utils/        formatting helpers ($B/$M, OI, %, strike)
  lib/          cn() + chart color/constants
  components/
    ui/         shadcn primitives (button, card, toggle, toggle-group, badge)
    dashboard/  MetricsStrip, MetricCard, StrikeProfile, NetGexSparkline,
                ScopeToggle, StatusBadge, Dashboard
  styles/       tailwind.css (tokens) + global.scss
```
