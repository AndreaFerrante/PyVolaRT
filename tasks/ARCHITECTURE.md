# ARCHITECTURE.md — System Architecture Design (GEX Dashboard)

> Design document. No implementation. Fulfills the design portion of `TODO.md` M7 (API & delivery contract) and adds the frontend/backend structural blueprint. Companion to `PLAN.md` (decisions D1–D8 referenced below).
>
> Stack: **React (TypeScript) + SCSS** · **Python FastAPI** · **ib_async** · **Postgres**.
> Consumers: **(a)** the React dashboard (human, visual), **(b)** an external service (machine — assumed to be the ES intraday framework consuming GEX regime/levels as its regime factor).

---

## 0. Architectural Principles

1. **One process, one IBKR session.** The acquisition engine, compute loop, and FastAPI app share a single asyncio event loop in a single process (single uvicorn worker). IBKR market-data lines belong to one session; multiple workers would each fight for them. Scaling the delivery tier (e.g., Redis pub/sub relay) is a documented later path, **out of scope for v1** (simplicity-first).
2. **Normalize at the edge.** Raw `ib_async` objects never cross into domain code. Every datum is converted to a Pydantic model at the acquisition boundary (NaN/sentinel cleanup, UTC timestamps, provenance tags). Everything downstream — state, engine, persistence, REST, WS — speaks only these models.
3. **`core/` is dependency-clean.** No FastAPI or ib_async imports in domain logic. The GEX engine is fixture-testable offline (M4) and replayable (M8) without a broker or a server.
4. **One contract, two consumers.** Frontend and external service consume the *same* versioned schema. TypeScript types are **generated** from the OpenAPI/JSON Schema export of the Pydantic models — never hand-synced.
5. **Push is canonical, pull is convenience.** The WS stream is the primary feed; REST serves bootstrap, history, and poll-style consumers. Both return identical model shapes.

---

## 1. Folder Structure

Mono-repo, sibling to the existing `tasks/` planning docs:

```
gex-dashboard/
├── tasks/                  # PLAN.md, TODO.md, ARCHITECTURE.md, lessons.md
├── backend/
└── frontend/
```

### 1.1 Backend (FastAPI + ib_async)

```
backend/
├── pyproject.toml
├── .env.example                    # ports, DB DSN, line cap, tier sizes, cadences
├── alembic/                        # schema migrations
│   └── versions/
├── app/
│   ├── main.py                     # app factory; lifespan starts/stops background tasks
│   ├── config.py                   # pydantic-settings; single config source (hashed into `runs`)
│   │
│   ├── api/                        # ── FastAPI surface (the ONLY FastAPI imports) ──
│   │   ├── deps.py                 # DI: state, hub, db session
│   │   └── v1/
│   │       ├── router.py
│   │       ├── rest/
│   │       │   ├── gex.py          # /gex/current /gex/levels /gex/flip-curve /gex/history
│   │       │   ├── quality.py      # /quality  (feed status)
│   │       │   ├── meta.py         # /meta/run /meta/config
│   │       │   └── health.py       # /healthz (liveness only)
│   │       └── ws/
│   │           ├── stream.py       # WS endpoint
│   │           └── manager.py      # connection registry, latest-wins backpressure
│   │
│   ├── core/                       # ── pure domain; no IO frameworks ──
│   │   ├── models/                 # Pydantic contract (§2) — the single source of truth
│   │   │   ├── contracts.py        # OptionContract, identifiers, enums
│   │   │   ├── market.py           # GreeksUpdate, UnderlyingQuote, OpenInterestRecord
│   │   │   ├── gex.py              # StrikeGex, GexSnapshot, GexLevels, FlipCurve
│   │   │   ├── quality.py          # DataQuality, FeedStatus
│   │   │   └── envelope.py         # WsEnvelope + message union
│   │   ├── state.py                # in-memory MarketState (conId-keyed, latest-value)
│   │   └── gex/
│   │       ├── engine.py           # per-strike, net/gross, walls, regime (PLAN §6)
│   │       ├── black_scholes.py    # own BS gamma (flip sweep + NaN fallback)
│   │       └── flip.py             # hypothetical-spot sweep, zero-crossing locator
│   │
│   ├── acquisition/                # ── the ONLY ib_async imports ──
│   │   ├── session.py              # connect/reconnect/re-subscribe lifecycle
│   │   ├── budget.py               # line-budget owner (D8): hard cap, accounting
│   │   ├── tiers.py                # tier scheduler, rotating snapshot pool, re-windowing
│   │   ├── chain.py                # reqSecDefOptParams, qualification, contract cache
│   │   ├── handlers.py             # tick callbacks → normalized models → MarketState
│   │   └── oi.py                   # once-daily OI fetch + cache (D3)
│   │
│   ├── orchestration/
│   │   ├── scheduler.py            # market-hours gating, session start/stop
│   │   ├── recompute.py            # dirty-flag → throttled compute loop (D5)
│   │   └── hub.py                  # in-process broadcast hub (publish/subscribe)
│   │
│   ├── persistence/
│   │   ├── db.py                   # engine/session management
│   │   ├── tables.py               # SQLAlchemy models (mirrors PLAN §8)
│   │   ├── writers.py              # snapshot/OI/greeks writers (hub subscriber)
│   │   └── retention.py            # nightly prune (keep N days)
│   │
│   └── observability/
│       ├── logging.py              # structured logs: lines-in-use, cadence, disconnects
│       └── metrics.py              # counters/gauges (recompute latency, WS clients…)
│
├── tests/
│   ├── fixtures/                   # known chain → known GEX (M4 regression)
│   ├── unit/                       # engine, budget, models/validators
│   ├── integration/                # API contract tests against a fake hub
│   └── replay/                     # recorded-session deterministic replay (M8)
└── scripts/
    ├── spike_m2.py                 # M2 feasibility spike entry point
    ├── record_session.py           # capture a session for replay tests
    └── export_openapi.py           # dump OpenAPI/JSON Schema for FE codegen
```

**Layering rule (enforceable by import-linter later):** `api → orchestration → core ← acquisition`; `persistence` subscribes to the hub; nothing imports `api`.

### 1.2 Frontend (React + TypeScript + SCSS)

Component inventory mirrors the approved mockup: an eight-card metrics strip over a Strike Profile chart with an All/Near scope toggle.

```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   ├── generated/              # types generated from backend OpenAPI (do not edit)
│   │   │   └── schema.d.ts
│   │   ├── rest.ts                 # bootstrap fetch (/gex/current), history
│   │   └── ws.ts                   # WS client: reconnect, seq-gap detect, envelope parse
│   ├── state/
│   │   └── gexStore.ts             # single store: snapshot, quality, connection state
│   ├── hooks/
│   │   ├── useGexFeed.ts           # WS lifecycle + REST bootstrap fallback
│   │   └── useStaleness.ts         # drives status indicators from DataQuality + seq age
│   ├── components/
│   │   ├── layout/
│   │   │   ├── DashboardGrid/      # page layout (metrics strip + profile panel)
│   │   │   └── StatusBar/          # feed status (LIVE/DEGRADED/STALE/…), last update
│   │   ├── metrics/
│   │   │   ├── MetricCard/         # generic: title, value, sub-label, accent color
│   │   │   └── MetricsStrip/       # 8 cards: Spot · Net GEX (+ratio) · Call GEX (+OI)
│   │   │                           #   · Put GEX (+OI) · Total GEX (+OI)
│   │   │                           #   · Call Wall (+%dist) · Put Wall (+%dist) · Zero Gamma
│   │   ├── charts/
│   │   │   ├── StrikeProfile/      # call (green, +) / put (red, −) bars per strike,
│   │   │   │                       #   dashed spot line, wall bars highlighted,
│   │   │   │                       #   All/Near scope toggle, legend
│   │   │   └── FlipCurve/          # phase-2 panel: net GEX vs hypothetical spot
│   │   └── common/
│   │       ├── ScopeToggle/        # "All" / "Near"
│   │       └── ValueDelta/         # formatted %, signed coloring
│   ├── styles/
│   │   ├── abstracts/              # _tokens.scss (dark theme palette: bg, green/red,
│   │   │                           #   accent blue), _mixins.scss, _functions.scss
│   │   ├── base/                   # _reset.scss, _typography.scss
│   │   └── main.scss
│   └── utils/
│       └── format.ts               # $34.9B / 1500.0M / +1.13% formatting, strike labels
└── tests/
```

**SCSS convention:** design tokens and mixins live in `styles/abstracts/`; each component co-locates a `Component.module.scss` importing the abstracts. Dark theme is the default token set (per mockup); theming stays a token swap.

---

## 2. Pydantic Contract (spec — the normalization layer)

> These definitions standardize the IBKR feed. Three groups: **ingestion** (IBKR → internal), **computed** (engine → consumers), **wire** (WS envelope). Pydantic v2. All timestamps **UTC-aware**. All identity is **`con_id`**; symbols/strikes are decoration.

### 2.0 Normalization rules (applied at the acquisition boundary)

- IBKR sentinels — `NaN`, `±inf`, `-1`-style "no value", `UNSET_DOUBLE` — are converted to `None` by field validators. **`None` means "unknown," never `0`.** Zero is a legitimate market value.
- Every greeks datum carries **provenance**: `basis` (which tick computation: model/bid/ask/last) and `source` (stream / snapshot / BS fallback) so the engine and quality layer can weigh inputs.
- **Units pinned once:** all GEX values are **USD gamma per 1% spot move** (`γ · OI · multiplier · S² · 0.01`). Per-strike values land in $M-scale, aggregates in $B-scale; formatting is a frontend concern.
- Sign convention (PLAN §6): option gamma is always ≥ 0; **the put leg is subtracted** under the dealer long-call/short-put assumption. `put_gex` is therefore ≤ 0 in all outputs.

### 2.1 Ingestion models — `core/models/contracts.py`, `market.py`

```python
class OptionRight(str, Enum):
    CALL = "C"
    PUT = "P"

class Tier(IntEnum):
    T1_STREAM = 1          # continuous NTM stream
    T2_FREQUENT = 2        # rotating pool, 30–60 s
    T3_INFREQUENT = 3      # far wings/expiries, 5–15 min

class OptionContract(BaseModel):
    """Reference identity for one option. Frozen value object."""
    model_config = ConfigDict(frozen=True)

    con_id: int                       # IBKR conId — the ONLY identity key
    symbol: str                       # "SPX"
    trading_class: str                # "SPX" | "SPXW"
    expiry: date
    strike: float
    right: OptionRight
    multiplier: int = 100
    exchange: str = "SMART"
```

```python
class GreeksBasis(str, Enum):
    MODEL = "model"; BID = "bid"; ASK = "ask"; LAST = "last"

class DataSource(str, Enum):
    STREAM = "stream"                 # Tier-1 live tick
    SNAPSHOT = "snapshot"             # Tier-2/3 rotation (or brief-stream-then-cancel)
    BS_FALLBACK = "bs_fallback"       # own Black-Scholes, used when broker greeks unusable

class GreeksUpdate(BaseModel):
    """One normalized tickOptionComputation. None == unknown (never 0)."""
    con_id: int
    ts: AwareDatetime                 # receipt time, UTC
    basis: GreeksBasis
    source: DataSource
    iv: float | None
    delta: float | None
    gamma: float | None
    vega: float | None
    theta: float | None
    opt_price: float | None
    und_price: float | None

    @field_validator("iv", "delta", "gamma", "vega", "theta",
                     "opt_price", "und_price", mode="before")
    @classmethod
    def _ibkr_sentinels_to_none(cls, v):
        """NaN / inf / UNSET_DOUBLE / negative-impossible → None."""
        ...
```

```python
class UnderlyingQuote(BaseModel):
    symbol: str                       # "SPX"
    ts: AwareDatetime
    last: float | None
    bid: float | None
    ask: float | None
    # spot resolution order: mid(bid,ask) → last; engine never reads raw fields

class OpenInterestRecord(BaseModel):
    """Once per contract per session (D3: OI is end-of-day data)."""
    con_id: int
    session_date: date
    open_interest: int                # ≥ 0
    fetched_at: AwareDatetime
```

### 2.2 Computed models — `core/models/gex.py`, `quality.py`

Field set matches the mockup exactly: separate call/put aggregates with OI, **net and gross** totals, call/put GEX ratio, walls, nullable zero-gamma.

```python
class Regime(str, Enum):
    LONG_GAMMA = "long_gamma"         # net > 0 → vol-suppressing
    SHORT_GAMMA = "short_gamma"       # net < 0 → vol-amplifying
    UNKNOWN = "unknown"               # insufficient data quality

class StrikeGex(BaseModel):
    """One bar of the Strike Profile chart."""
    strike: float
    call_gex: float                   # ≥ 0, USD per 1% move
    put_gex: float                    # ≤ 0 (sign from dealer assumption)
    net_gex: float                    # call_gex + put_gex
    call_oi: int
    put_oi: int
    quality: float                    # 0–1: share of inputs fresh & broker-sourced

class GexLevels(BaseModel):
    zero_gamma: float | None          # None when no crossing in range (mockup: "N/A")
    call_wall: float | None           # strike of max positive concentration
    put_wall: float | None            # strike of max negative concentration
    call_wall_dist_pct: float | None  # vs spot, e.g. +1.13
    put_wall_dist_pct: float | None   # e.g. −0.77

class GexSnapshot(BaseModel):
    """The primary product. One per recompute (2–5 s)."""
    ts: AwareDatetime
    underlying: str                   # "SPX"
    spot: float
    net_gex: float                    # call_total + put_total  (−$14.7B in mockup)
    gross_gex: float                  # call_total + |put_total| ($34.9B in mockup)
    call_gex_total: float             # ≥ 0   ($10.1B)
    put_gex_total: float              # ≤ 0   (−$24.8B)
    call_oi_total: int
    put_oi_total: int
    total_oi: int
    gex_ratio: float | None           # call_total / |put_total|  (0.41)
    regime: Regime
    levels: GexLevels
    profile: list[StrikeGex]          # full computed range; FE filters All/Near
    expiries_included: list[date]
    quality: DataQuality

class FlipCurvePoint(BaseModel):
    spot: float                       # hypothetical S'
    net_gex: float                    # own-BS re-priced (PLAN §6, sticky-strike D7)

class FlipCurve(BaseModel):
    ts: AwareDatetime
    points: list[FlipCurvePoint]
    zero_crossing: float | None       # authoritative source of GexLevels.zero_gamma
```

```python
class FeedStatus(str, Enum):
    LIVE = "live"                     # spot fresh, T1 coverage ≥ threshold
    DEGRADED = "degraded"             # partial coverage / fallbacks active
    STALE = "stale"                   # spot or T1 older than SLA
    OFFLINE_HOURS = "offline_hours"   # scheduler-gated (market closed)
    DISCONNECTED = "disconnected"     # IBKR session down

class DataQuality(BaseModel):
    status: FeedStatus
    t1_coverage: float                # fraction of T1 contracts with fresh greeks
    spot_age_s: float | None
    oi_session_date: date | None      # which session's OI is in use
    lines_in_use: int
    line_cap: int                     # assertion surface for D8
```

### 2.3 Wire envelope — `core/models/envelope.py`

Discriminated union (clean TS codegen). `seq` is monotonic per run; consumers detect gaps/restarts.

```python
class GexSnapshotMsg(BaseModel):
    kind: Literal["gex_snapshot"] = "gex_snapshot"
    data: GexSnapshot

class FlipCurveMsg(BaseModel):
    kind: Literal["flip_curve"] = "flip_curve"
    data: FlipCurve

class QualityMsg(BaseModel):
    kind: Literal["quality"] = "quality"   # pushed immediately on status change
    data: DataQuality

class HeartbeatMsg(BaseModel):
    kind: Literal["heartbeat"] = "heartbeat"
    data: AwareDatetime                    # lets consumers tell "quiet" from "dead"

WsMessage = Annotated[
    GexSnapshotMsg | FlipCurveMsg | QualityMsg | HeartbeatMsg,
    Field(discriminator="kind"),
]

class WsEnvelope(BaseModel):
    v: Literal[1] = 1                 # schema version; additive-only within v1
    seq: int
    sent_at: AwareDatetime
    msg: WsMessage
```

---

## 3. Data Flow — Provider → FastAPI → Frontend / External App

### 3.1 Topology

```
        IBKR Gateway (headless, IBC daily re-auth)
                 │  TCP
                 ▼
   ┌─ acquisition/ ───────────────────────────────┐
   │ session ─ budget(≤100 lines) ─ tiers/rotation │
   │ handlers: raw ticks → Pydantic (§2.1)         │
   └───────────────┬───────────────────────────────┘
                   ▼
        core/state  MarketState            oi.py → daily OI cache
        (conId → latest greeks/quote)      (once per session, D3)
                   │  dirty flag on spot / T1 update
                   ▼
        orchestration/recompute (throttled 2–5 s, D5)
        core/gex engine → GexSnapshot (+ FlipCurve @15–30 s)
                   │ publish
                   ▼
        orchestration/hub  (in-process broadcast)
            ├──► api/ws manager ──► React dashboard      (push)
            │                   └─► External service     (push)
            └──► persistence/writers ──► Postgres
                                            ▲
        api/rest ── /current,/levels (memory) ─ /history (PG)
            ▲                ▲
        React bootstrap   External service (poll option)
```

### 3.2 Stage by stage

**Stage 1 — Acquire & normalize.** `ib_async` callbacks fire on every tick. `handlers.py` immediately converts each raw object into `GreeksUpdate` / `UnderlyingQuote` (sentinel cleanup, UTC stamp, `basis`/`source`/tier tags) and writes it into `MarketState` — a flat, conId-keyed latest-value store. The subscription manager (`budget.py` + `tiers.py`) is the only component that opens/closes lines: Tier 1 streams the NTM window; Tier 2/3 cycle through the fixed rotating pool; re-windowing follows spot drift. `oi.py` populates the OI cache once at session start (D3) — OI never moves intraday.

**Stage 2 — Compute (throttled).** Spot ticks and Tier-1 greeks updates only set a dirty flag. The recompute loop wakes on its 2–5 s cadence, takes a consistent read of `MarketState` + OI cache, and runs the engine: per-strike call/put GEX, net/gross totals, ratio, walls, regime, and quality scoring (fresh-vs-stale, broker-vs-fallback). The flip-curve sweep (own BS over hypothetical spots) runs on its own slower cadence (~15–30 s) since it's spot-grid pricing, and its zero crossing feeds `GexLevels.zero_gamma`. Output: one immutable `GexSnapshot`.

**Stage 3 — Distribute (fan-out).** The snapshot is published once to the in-process hub. Two subscriber classes:
- **WS manager** wraps it in `WsEnvelope` (seq, v) and fans out to every connected client — the React dashboard and the external service are *peers on the same stream*. Backpressure is **latest-wins**: each connection holds an outbound buffer of one snapshot; if a client is slow, intermediate snapshots are dropped, never queued unboundedly. `QualityMsg` (status changes) bypasses coalescing. Heartbeats every 10 s.
- **Persistence writer** appends to `gex_snapshots` (every recompute) and coarse `greeks_snapshots` (throttled), inside the retention policy.

**Stage 4 — Serve on demand (REST).**

| Endpoint | Returns | Source | Intended consumer |
|---|---|---|---|
| `GET /api/v1/gex/current` | `GexSnapshot` | memory (last published) | FE bootstrap; external poll |
| `GET /api/v1/gex/levels` | `GexLevels` + regime + spot + ts + quality | memory | **external service fast path** (regime factor without parsing profiles) |
| `GET /api/v1/gex/flip-curve` | `FlipCurve` | memory | FE phase-2 panel |
| `GET /api/v1/gex/history?from&to&step` | `list[GexSnapshot]` (downsampled) | Postgres | replay/analysis |
| `GET /api/v1/quality` | `DataQuality` | memory | monitoring, external gating |
| `GET /api/v1/meta/run` | run id, config hash, line cap | memory | reproducibility |
| `WS /api/v1/ws/stream` | `WsEnvelope` stream | hub | FE + external push |
| `GET /healthz` | liveness | — | process supervision |

`current`/`levels` responses carry the snapshot `seq` (also as `ETag`), so a polling external service can cheaply detect "no change."

**Stage 5 — Consumption patterns.**
- **Frontend:** on load, REST-bootstrap from `/gex/current`, then attach the WS. `useGexFeed` reconciles by `seq` (WS frame older than bootstrap is discarded). `useStaleness` drives the StatusBar straight from `DataQuality` + envelope age — the UI always *shows* when it's lying about freshness. All/Near toggle filters the delivered full profile client-side; no extra round trip.
- **External service:** two supported modes, same schema. *Push:* subscribe to the WS, consume `gex_snapshot`/`quality`. *Pull:* poll `/gex/levels` at its own cadence (regime, flip, walls, spot, quality — the minimal set the ES framework's regime factor needs). Recommendation: pull for the trading framework — it decouples its loop from feed hiccups and lets it gate on `quality.status` explicitly.

### 3.3 Cadence summary

| Flow | Cadence | Notes |
|---|---|---|
| Spot / T1 greeks → state | per tick | sets dirty flag only |
| T2 rotation | 30–60 s | within rotating pool, throttled vs pacing |
| T3 rotation | 5–15 min | far wings/expiries |
| OI fetch | once per session | D3; cached, never re-polled intraday |
| Recompute → `GexSnapshot` | 2–5 s | only if dirty |
| Flip sweep → `FlipCurve` | 15–30 s | own-BS grid |
| WS push | on recompute | latest-wins per client |
| Heartbeat | 10 s | always, incl. off-hours |
| Persistence | per recompute | + nightly retention prune |

### 3.4 Degradation semantics (contract, not best-effort)

- **IBKR disconnect:** quality → `DISCONNECTED` pushed immediately; last snapshot stays served via REST, flagged stale; on reconnect, acquisition re-subscribes all tiers, refreshes OI if the session date rolled, quality recovers through `DEGRADED` → `LIVE` as T1 coverage rebuilds.
- **Partial data (NaN wings, fallbacks active):** snapshot still produced; `StrikeGex.quality` and `t1_coverage` make the degradation measurable instead of silent.
- **Off-hours:** scheduler gates acquisition; status `OFFLINE_HOURS`; REST serves the last session's final snapshot; heartbeats continue so consumers know the service itself is alive.
- **Consumer rule of thumb:** *the external service should treat anything but `LIVE`/`DEGRADED` as "no regime signal"* rather than acting on stale gamma.

### 3.5 Cross-cutting notes

- **Schema discipline:** `v` in the envelope + `/api/v1` path; only additive changes within v1. `scripts/export_openapi.py` regenerates `frontend/src/api/generated/schema.d.ts` — the codegen step is part of CI, so contract drift fails the build, not the user.
- **Auth (optional, cheap):** a static bearer token checked on WS upgrade and REST for the external service; full authn/z stays out of v1 scope per PLAN §2.
- **Run reproducibility:** every process start writes a `runs` row (config hash, line cap); `seq` resets per run, which is exactly how consumers detect restarts.

---

## 4. Open Items (need your confirmation)

1. **External service transport** — design supports both; I recommend REST-poll of `/gex/levels` for the ES framework. Confirm, and state its desired poll cadence.
2. **"Near" window definition** — mockup toggle implies a fixed near-range (e.g., spot ±N strikes). Client-side filter per this design, but confirm N (proposal: same ±30 as Tier 1).
3. **Bearer-token auth for the external consumer** — yes/no for v1.
4. **History retention horizon** — proposal: 30 days of `gex_snapshots` at full cadence, then prune (PLAN §8 left N open).
