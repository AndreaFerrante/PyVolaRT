# GEX Dashboard — Backend

FastAPI service that computes semi-real-time Gamma Exposure (GEX) from an options
feed and serves it to two peers on one versioned schema: the React dashboard and
an external service (the ES trading framework). Push (WebSocket) is the canonical
feed; REST serves bootstrap, history, and poll-style consumers.

See `../tasks/PLAN.md`, `../tasks/TODO.md`, and `../tasks/ARCHITECTURE.md` for the
decisions behind this layout.

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # base runtime is enough for simulated mode

uvicorn app.main:app --reload            # http://127.0.0.1:8000
```

Out of the box it runs the **simulated** provider — a Black-Scholes-derived,
mockup-shaped option universe with no broker connection — so the whole pipeline
(compute → hub → WebSocket/REST) and the frontend can be developed end-to-end.

- OpenAPI docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/healthz

## Providers

| `GEX_PROVIDER` | Source | Notes |
| --- | --- | --- |
| `simulated` (default) | in-process simulator | no broker; runs anywhere |
| `ibkr` | live IB Gateway/TWS via `ib_async` | **M2-gated**; requires `pip install ib_async` and a running Gateway. Correctness against a live feed is not yet validated (see PLAN.md). |

Switch with an env var (no code change):

```bash
GEX_PROVIDER=ibkr uvicorn app.main:app
```

> Run a **single** uvicorn worker. Market-data lines belong to one IBKR session;
> multiple workers would fight over the 100-line budget.

## Configuration

All settings use the `GEX_` prefix and can come from the environment or a `.env`
file. See `.env.example`. Common ones:

- `GEX_DATABASE_URL` — SQLite by default; Postgres via
  `postgresql+asyncpg://user:pass@host:5432/gex`
- `GEX_HISTORY_RETENTION_DAYS` — snapshots older than this are pruned hourly (default 7)
- `GEX_UNDERLYING`, `GEX_STRIKE_SPACING`, `GEX_NTM_STRIKES_EACH_SIDE`
- `GEX_RECOMPUTE_INTERVAL_S`, `GEX_HEARTBEAT_INTERVAL_S`
- `GEX_CORS_ORIGINS` — JSON list, e.g. `["http://localhost:5173"]`

## API (under `/api/v1`)

| Method | Path | Returns | For |
| --- | --- | --- | --- |
| GET | `/gex/current` | `GexSnapshot` | FE bootstrap; external poll |
| GET | `/gex/levels` | `LevelsResponse` | external service fast path (regime/walls) |
| GET | `/gex/flip-curve` | `FlipCurve` | FE phase-2 panel |
| GET | `/gex/history?start&end&underlying&limit&step` | `list[GexSnapshot]` | replay/analysis (Postgres/SQLite) |
| GET | `/quality` | `DataQuality` | monitoring / external gating |
| GET | `/meta/run` | run id + config hash | reproducibility |
| WS | `/ws/stream` | `WsEnvelope` stream | FE + external push |
| GET | `/healthz` | liveness | supervision |

The WebSocket sends a **bootstrap** (latest snapshot + quality) on connect, then
streams snapshots, flip curves, quality changes, and ~10 s heartbeats. Each
envelope carries `v` (schema version) and a monotonic `seq` so clients can detect
gaps and restarts.

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

`tests/test_smoke.py` boots the app on the simulated provider and exercises the
REST endpoints and the WebSocket bootstrap with no external infra.

## Layout

```
app/
  api/            FastAPI surface — the only FastAPI imports (routes + WS)
  core/           pure domain: Pydantic models + GEX engine (no IO frameworks)
  services/       providers (IBKR / simulated), market state, hub, pipeline
  persistence/    SQLAlchemy tables + repository (history)
```

Layering: `api → services(pipeline) → core ← providers`; `persistence` is driven
by the pipeline; nothing imports `api`. The IBKR integration is isolated behind
the provider interface so an M2 finding never ripples past `MarketState`.
