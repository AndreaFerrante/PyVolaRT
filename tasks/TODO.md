# TODO.md — Semi-Real-Time GEX Dashboard (fulfills `PLAN.md`)

> Macro milestones (M0–M9) with micro tasks. No code yet. Order matters: **M2 is a hard gate** — do not lock the acquisition architecture until its unknowns are answered. Each macro ends with an explicit **Exit / Verify** check (nothing is "done" without proof).

**Legend:** `[ ]` open · `[~]` in progress · `[x]` done · 🔒 hard gate · ⏸ deferred (later phase)

---

## ✅ Pre-flight: Plan Verification Gate

- [ ] Confirm underlying = **SPX index options** (vs options-on-ES futures)
- [ ] Confirm expiry set: front + current-week dailies + nearest monthly (configurable)
- [ ] Confirm line cap assumption = **100** (no Quote Booster in v1)
- [ ] Confirm semi-real-time SLAs: NTM 2–5 s · near-wings 30–60 s · far 5–15 min · OI daily
- [ ] Sign off `PLAN.md` §3 decisions (D1–D8) and §7 architecture
- [ ] Create `tasks/lessons.md` and seed it with the M2 unknowns to be resolved

---

## M0 — Environment, Entitlements & Connectivity

*Goal: a live quote and one option's model greeks arriving over the API. Nothing downstream works until this holds.*

**Account & data entitlements**
- [ ] Verify account flagged **non-professional** (Client Portal → Market Data Subscriptions → Subscriber Status)
- [ ] Sign **Market Data API Acknowledgement** (off-platform data gate)
- [ ] Subscribe **US Securities Snapshot and Futures Value Bundle** (prerequisite)
- [ ] Subscribe **OPRA (US Options)** real-time
- [ ] Subscribe **US Equity and Options Add-On Streaming Bundle** (snapshot → streaming)
- [ ] Confirm **SPX index level** data entitlement (Cboe/index)
- [ ] Confirm account funded enough to release real-time data

**Runtime**
- [ ] Install **IB Gateway** (headless); enable API port; set trusted IP / client-id policy
- [ ] Install & configure **IBC** for daily auto-login/restart
- [ ] Create Python env; install **`ib_async`** (successor to `ib_insync`)
- [ ] Decide live vs paper port; document both (avoid simultaneous-login data conflict)

**Exit / Verify 🔒**
- [ ] Connect via `ib_async`; receive a live **SPY** quote over the API
- [ ] Receive a live **SPX** index level over the API
- [ ] Receive `tickOptionComputation` model greeks for **one** SPX option
- [ ] Record exact subscription names + monthly costs + waiver thresholds in `lessons.md`

---

## M1 — Contract Universe & Chain Discovery

*Goal: build, qualify, and cache the contract set for the selected expiries/strikes.*

- [ ] Resolve underlying contract (SPX index) + multiplier + trading class
- [ ] Call `reqSecDefOptParams`; capture expirations + strikes (avoid `reqContractDetails` for full chains)
- [ ] Implement **expiry selection** logic (front / week / nearest monthly; configurable)
- [ ] Implement **strike selection** logic (NTM ±N around live spot; $5 spacing assumption)
- [ ] Qualify selected option contracts (resolve conIds); handle ambiguous/duplicate contract-type returns
- [ ] Define the **NTM window band** + recenter threshold parameters
- [ ] Persist contract reference data → `contracts`

**Exit / Verify**
- [ ] Front-expiry NTM call+put set enumerated, qualified, and stored
- [ ] Spot-change simulation produces a correct recentered strike set (offline check)

---

## M2 — Acquisition Feasibility Spike 🔒 (HARD GATE)

*Goal: answer every IBKR unknown before committing the architecture. Output is a decision doc, not features.*

- [ ] Validate **streamed greeks**: gamma/IV arrive and update for NTM SPX options
- [ ] Validate **OI for index options**: does generic tick **101** / `callOpenInterest`+`putOpenInterest` populate for SPX? Confirm exact field/tick
- [ ] Validate **OI is static intraday** (confirm it does not move during the session)
- [ ] Validate **snapshot greeks**: does `snapshot=True` return model greeks reliably? If not → confirm **brief-stream-then-cancel** as the Tier-2/3 mechanism
- [ ] Characterize **NaN / stale** behavior on illiquid wing strikes
- [ ] Measure realistic **line consumption** and time-to-populate for a NTM batch
- [ ] Probe **pacing**: find a safe steady request rate well under ~50/s; observe error code 100 behavior (do **not** trip the 3-violation disconnect)
- [ ] Confirm greeks require **both** option and underlying subscriptions (per IBKR docs)

**Exit / Verify 🔒**
- [ ] Written yes/no + workaround for each unknown above, logged in `lessons.md`
- [ ] **Acquisition approach locked** (true snapshot vs brief-stream-then-cancel; OI source)
- [ ] Go/no-go decision on architecture recorded; if any blocker, **re-plan before proceeding**

---

## M3 — Line-Budget & Subscription Manager

*Goal: the budget owner + tier scheduler + rotation + in-memory state. Core IP.*

**Budget & state**
- [ ] Implement **line-budget owner**: count active lines; refuse subscriptions that exceed cap (D8)
- [ ] Implement **in-memory market state**: latest greeks/IV/OI/spot per contract
- [ ] Wire **tick handlers** to route greeks, OI, and spot into state

**Tiering & rotation**
- [ ] Tier 1 — continuous stream of front-expiry NTM (±N × 2 rights)
- [ ] Tier 2 — **fixed rotating pool** (~35 lines) cycling NTM of next expiries + near-wings
- [ ] Tier 3 — low-frequency rotation of far wings/expiries
- [ ] Implement **throttled batch rotation** (respect M2-validated safe rate)
- [ ] Implement **NTM re-windowing**: release exited strikes, subscribe entered strikes, throttled at the band boundary
- [ ] **Daily OI fetch** at session start; cache; no intraday re-poll (D3)
- [ ] Apply NaN/stale handling at the state layer (mark unusable; flag for BS fallback)

**Exit / Verify**
- [ ] All tiers run concurrently within budget over a session segment
- [ ] **Assertion: active lines ≤ cap** holds continuously (instrumented)
- [ ] Recenter works on real spot drift without churn or budget breach
- [ ] No pacing disconnects during a sustained rotation run

---

## M4 — GEX Computation Engine

*Goal: per-strike + total + walls + flip curve. Pure-ish and fixture-testable offline.*

- [ ] Implement **per-strike dollar gamma** (`γ·OI·m·S²·0.01`)
- [ ] Implement **net GEX** with explicit **dealer long-call / short-put sign convention** (subtract put leg; document that gamma itself is ≥0)
- [ ] Implement **call wall / put wall** detection (largest +/− gamma concentration)
- [ ] Implement **regime flag** (net long-gamma vs short-gamma)
- [ ] Implement **own Black-Scholes gamma** (`γ = φ(d1)/(S·σ·√t)`) using IBKR per-strike IV
- [ ] Implement **flip-curve sweep**: re-price gamma across hypothetical spot grid (sticky-strike, D7); locate zero crossing
- [ ] Build **offline fixtures** (known chain → known GEX) for regression
- [ ] Implement **BS fallback** for strikes with stale/NaN broker greeks; clip strikes lacking IV

**Exit / Verify**
- [ ] Engine reproduces fixture outputs deterministically
- [ ] Flip level from sweep matches an independent manual calculation on a fixture
- [ ] Own-BS gamma tracks IBKR streamed gamma for sample NTM strikes (reconciliation)
- [ ] Sign convention unit-tested (inverting put leg flips total GEX as expected)

---

## M5 — Persistence Layer (Postgres)

*Goal: store reference data, daily OI, and computed snapshots — not raw tick spam.*

- [ ] Define schema for `contracts`, `oi_daily`, `greeks_snapshots`, `gex_snapshots`, `runs` (per `PLAN.md` §8)
- [ ] Implement **daily OI cache** writer/reader (one row per contract per session date)
- [ ] Implement **GEX snapshot** writer (each recompute: total, flip, walls, profile JSON, spot, regime)
- [ ] Implement **coarse greeks snapshot** writer (NTM, throttled — not every tick)
- [ ] Partition time-series tables **by day**
- [ ] Implement **retention** (keep N days; archive/drop older)
- [ ] Record `runs` metadata (config hash, line cap, start/stop) for reproducibility

**Exit / Verify**
- [ ] GEX snapshots persist and reload identically (round-trip)
- [ ] OI cached exactly once per session date; no intraday duplication
- [ ] Retention prunes correctly; write volume stays bounded over a full session

---

## M6 — Orchestration & Operational Lifecycle

*Goal: unattended open-to-close operation that survives disconnects and the daily restart.*

- [ ] Implement **session scheduler** (start at open, stop at close; respect SPX options hours)
- [ ] Implement **auto-reconnect** on disconnect
- [ ] Implement **re-subscribe**: rehydrate all tiers + re-fetch OI if stale after reconnect
- [ ] Integrate with **IBC** daily restart; detect reconnection and rehydrate
- [ ] Implement **pacing safety**: queue/throttle to the M2-validated rate; guard the 3-violation rule
- [ ] Implement **startup OI fetch** hook (session start / post-settlement)
- [ ] Add structured **logging** (subscriptions, line count, recompute cadence, disconnects)

**Exit / Verify**
- [ ] Survives a **forced disconnect** → reconnect → full rehydrate, unattended
- [ ] Survives a **daily Gateway restart** (IBC) with automatic recovery
- [ ] Recompute cadence stays within SLA across the session

---

## M7 — API & Delivery Contract ⏸ (design now, build later)

*Goal: freeze the FastAPI + WebSocket contract. No implementation in this phase.*

- [ ] Define **WebSocket payload schema** (total GEX, flip level, walls, per-strike profile, spot, regime, timestamp)
- [ ] Define **REST endpoints** (current snapshot; historical snapshot range for replay)
- [ ] Define **update cadence / message envelope** contract for the frontend
- [ ] Define **error/stale-data semantics** (how the feed signals degraded/NaN state)
- [ ] Review & **freeze** the contract doc

**Exit / Verify**
- [ ] Reviewed, frozen API + WS schema document committed
- [ ] **No implementation** produced (explicitly deferred)

---

## M8 — Validation, Reconciliation & Hardening

*Goal: prove the whole pipeline is correct and durable.*

- [ ] **Reference cross-check**: total-GEX sign, profile shape, flip level vs a public GEX reference for the same day (match shape/regime, not scalar)
- [ ] **Broker-vs-own-BS** gamma reconciliation across a strike sample
- [ ] **OI sanity** pass (magnitudes plausible; no all-zero/NaN feeding GEX)
- [ ] **Line-budget assertion** verified over a full session
- [ ] **Replay test**: record a session; deterministically replay through the engine
- [ ] **Full-session soak**: one clean open-to-close run incl. daily restart; check for leaks/disconnects/cadence drift
- [ ] Log all findings + fixes in `lessons.md`

**Exit / Verify**
- [ ] All `PLAN.md` §11 checks pass
- [ ] One clean open-to-close soak with no pacing disconnects and stable cadence

---

## M9 — Frontend Dashboard ⏸ (later phase)

*Goal: React views over the WebSocket feed. Deferred until backend is validated.*

- [ ] Per-strike **GEX profile** chart (positive/negative by strike)
- [ ] **Zero-gamma / flip level** marker vs spot
- [ ] **Call wall / put wall** annotations
- [ ] **Total GEX + regime** indicator (long- vs short-gamma)
- [ ] Connect to WebSocket feed; render at SLA cadence
- [ ] Display the **dealer-positioning assumption** disclaimer (per §6 sign note)

**Exit / Verify**
- [ ] Live dashboard renders profile, flip level, and walls from the real feed

---

## Review Log

*(Append a short review section per milestone as it completes: what changed, what was proven, what surprised us. Promote every surprise into a rule in `tasks/lessons.md`.)*

- M0 — _pending_
- M1 — _pending_
- M2 — _pending_ (gate findings go here + `lessons.md`)
- …
