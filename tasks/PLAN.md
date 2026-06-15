# PLAN.md — Semi-Real-Time GEX Dashboard (IBKR, Hybrid Acquisition)

> Strategic plan. No code. Implementation (`ib_async` data layer, FastAPI, React) follows after this plan is approved. `TODO.md` decomposes this into macro → micro tasks.

---

## 1. Objective

Build a **semi-real-time Gamma Exposure (GEX) dashboard** for **SPX index options** sourced from IBKR via the Python API (`ib_async`). Deliver dealer-gamma analytics — total GEX, per-strike GEX profile, zero-gamma (flip) level, call/put walls — refreshed on a few-second cadence, using a **hybrid acquisition strategy** that lives within the 100 market-data-line constraint.

**"Semi-real-time" service levels (targets, tunable):**
- Near-the-money (NTM) analytics: recompute every **2–5 s**.
- Wing strikes / far expiries: refresh every **30–60 s** (near-wings) to **5–15 min** (far).
- Open interest: refreshed **once per trading day** (it is end-of-day data — see D3).

This is explicitly **not** a tick-by-tick product. It is a positioning/structure dashboard.

---

## 2. Scope & Non-Goals

**In scope (v1):**
- Single underlying: **SPX** (validate plumbing on SPY first — see D1).
- Near-dated expiries only (front + current-week dailies + nearest monthly; configurable).
- Hybrid streaming + snapshot acquisition under a strict line budget.
- GEX compute engine (current-state from broker greeks; flip-curve from own Black-Scholes).
- Postgres persistence of reference data, daily OI, and computed GEX snapshots.
- Orchestration: session scheduling, reconnect/re-subscribe, market-hours gating.
- API delivery **contract** (FastAPI + WebSocket) — **designed** in v1, **implemented** in a later phase.

**Non-goals (v1):**
- Order execution / any trading action.
- Multiple simultaneous underlyings.
- Second-order exposures (vanna / charm / DEX / speed) — stretch goal, not v1.
- Tick-level persistence of every greek update.
- Historical GEX backfill beyond what we record live.
- Multi-user auth / production hardening of the web tier.
- React frontend build (last phase; contract designed now, built later).

---

## 3. Key Design Decisions (with rationale)

| # | Decision | Rationale |
|---|----------|-----------|
| **D1** | Target **SPX index options**; build & validate the pipeline on **SPY** first, then re-point at SPX. | SPX is the GEX benchmark and aligns with the ES/SPX trading thesis. SPY is more liquid with cleaner greeks/OI per strike, so it de-risks plumbing and gives a sanity reference before committing to SPX quirks. |
| **D2** | Greeks for **current state** come from IBKR streamed `modelGreeks` (`tickOptionComputation`). Greeks for the **flip-curve sweep** are computed with our **own Black-Scholes**, using IBKR's per-strike implied vol. | Broker greeks are authoritative for "now." The flip curve requires gamma evaluated at *hypothetical* spot levels, which only a model can produce. Mixing gives accuracy where it matters and analytical flexibility where it's needed. |
| **D3** | **Open interest is fetched once per day and cached.** | OI is end-of-day data published by the OCC after settlement; it does **not** update intraday. Polling it live wastes lines and yields nothing new. The only live inputs intraday are **spot** and **gamma**. |
| **D4** | **Three-tier acquisition** (continuous stream / frequent snapshot / infrequent snapshot), tiered by *gamma materiality* and *spot-sensitivity*. | Concentrates the scarce 100 lines where gamma is large and fast-moving (NTM, front expiry) and rotates the rest cheaply through the wings. |
| **D5** | **Recompute on a throttled timer, not per tick.** Mark state dirty on spot/gamma updates; recompute on a fixed interval. | Avoids tick-storm recompute. GEX does not need sub-second resolution; a 2–5 s cadence is indistinguishable for positioning analysis and far cheaper. |
| **D6** | **IB Gateway (headless) + IBC** for unattended operation. | TWS GUI is unnecessary for a data service. IB Gateway is lighter, but logs out daily for re-auth; IBC automates the daily restart/login so the service survives unattended. |
| **D7** | **Sticky-strike IV** assumption for the flip-curve sweep (hold each strike's IV fixed across the hypothetical-spot sweep). | The simplest defensible vol assumption; consistent with common public GEX methodologies. Documented as a known simplification and isolated so it can be upgraded to a surface-shift later. |
| **D8** | **One source of truth for the line budget**: a subscription manager that counts active lines and refuses to exceed the cap. | Line exhaustion silently kills data and triggers pacing disconnects. Centralizing the budget makes it auditable and assert-able. |

> **Assumptions to confirm before build:** (a) SPX is the intended underlying vs options-on-ES futures; (b) the expiry set (front + week + nearest monthly) matches the analytical intent; (c) account is/will be flagged **non-professional** with the Market Data API acknowledgement signed; (d) line cap is the default **100** (no Quote Booster yet).

---

## 4. The Central Constraint — Market-Data-Line Budget

IBKR grants **100 concurrent market-data lines by default** (scales with commissions/equity; Quote Booster adds more). Every streamed contract = one line. Pacing limit is ~**50 requests/second** at 100 lines; three pacing violations terminate the session. The budget — not the API — decides feasibility.

**Worked allocation (illustrative; tune empirically):**

| Bucket | Lines | Contents |
|--------|------:|----------|
| Underlying (SPX index) | 1 | Spot for `S` and S²term |
| VIX (optional context) | 1 | Regime context only |
| Overhead / reserve | ~3 | Headroom to avoid hard cap |
| **Tier 1 — continuous** | ~60 | Front/dominant expiry, NTM **±30 strikes × 2 rights** |
| **Tier 2 — rotating snapshot pool** | ~35 | Fixed reserve through which Tier-2/3 contracts are cycled |
| **Total active** | **≤ ~100** | Never exceeded |

**Key framing:** snapshots also occupy lines *while active*. We therefore treat Tier-2 as a **fixed-size rotating pool** (≈35 lines) that contracts cycle through in batches — we never let total active subscriptions exceed the cap, streaming + snapshotting combined.

At SPX ≈ 6000 with $5 NTM strike spacing, ±30 strikes ≈ **±$150 (±2.5%)** continuously streamed — comfortably covering where front-expiry / 0DTE gamma concentrates.

---

## 5. Hybrid Acquisition Strategy (detail)

Windowing has **two dimensions**: **strike** (NTM vs wings) and **expiry** (near vs far).

**Tier 1 — Continuous stream (live gamma + spot):**
- Front / dominant expiry (incl. 0DTE), NTM ±N strikes, both rights.
- Greeks update on tick; this is where gamma is largest and most spot-sensitive.

**Tier 2 — Frequent snapshot (~30–60 s):**
- NTM of the next 1–2 expiries + near-wings of the front expiry.
- Cycled through the rotating pool in throttled batches.

**Tier 3 — Infrequent snapshot (~5–15 min, or once):**
- Far wings / far expiries. Gamma is small and slow-moving; contribution to near-term dealer gamma is minor.
- **OI for all tiers fetched once daily** and cached (D3).

**Recompute trigger:** a spot tick or a Tier-1 gamma update marks the GEX state dirty; a fixed-interval timer (D5) recomputes from the in-memory current state, using the most recent snapshot gamma for wings.

**Re-windowing:** when spot drifts beyond a band, recenter the NTM window — release strikes that left the window, subscribe strikes that entered, all within the budget. Recentering is itself throttled to avoid churn near a boundary.

---

## 6. GEX Methodology (explicit, since conventions vary)

**Per-strike dollar gamma (per 1% move):**
`Gamma$(K) = γ(K) · OI(K) · multiplier · S² · 0.01`
where `γ` is option gamma, `OI` open interest, `multiplier` the contract multiplier (100), `S` spot.

**Net dealer GEX (standard "dealer long calls / short puts" assumption):**
`GEX = Σ_calls [γ · OI · m · S² · 0.01] − Σ_puts [γ · OI · m · S² · 0.01]`

- **Sign note (easy to get wrong):** option gamma is **always ≥ 0** for both calls and puts (and is symmetric at a matched strike). The **sign in GEX comes from the dealer-positioning assumption**, not the greek — we subtract the put leg. This assumption is exactly that: an assumption. It is stated on the dashboard.
- The scalar (`S²·0.01` for "per 1%", or `m·S` for "per point") is a **presentation choice**. The **shape** and the **zero crossing** are what carry signal and are convention-robust.

**Derived metrics:**
- **Total GEX** — net dealer gamma; sign indicates long-gamma (vol-suppressing) vs short-gamma (vol-amplifying) regime.
- **Per-strike profile** — the bar chart; positive vs negative contribution by strike.
- **Call wall / Put wall** — strikes of largest positive / negative gamma concentration (common support/resistance reads).
- **Zero-gamma (flip) level** — the spot at which net GEX crosses zero.

**Flip level — proper computation (not naive scaling):**
- Naively scaling existing per-strike gamma by S² is **wrong**, because gamma itself depends on S (peaked at ATM, decaying away).
- Correct: re-evaluate each option's **Black-Scholes gamma at a sweep of hypothetical spot levels** `S'`, holding IV (per strike, sticky-strike per D7), time-to-expiry, and rate fixed; recompute net GEX(`S'`); locate the zero crossing.
  - BS gamma: `γ = φ(d1) / (S' · σ · √t)`, `d1 = [ln(S'/K) + (r + σ²/2)·t] / (σ·√t)`, `φ` = standard normal pdf.
  - IV (`σ`) per strike comes from IBKR `modelGreeks.impliedVol`.
- This is a few thousand vectorized BS evaluations per refresh — microseconds; trivial at a 2–5 s cadence.

---

## 7. Architecture (data flow)

```
IB Gateway (TCP, headless)            IBC (daily re-auth / restart)
        │
        ▼
ib_async session  ──►  Subscription Manager  ──►  Tick Handlers
        │              (line-budget owner,         (route modelGreeks,
        │               tier scheduler,             OI, spot ticks)
        │               snapshot rotation)              │
        │                                                ▼
        │                                   In-Memory Market State
        │                                   (current greeks/OI/spot
        │                                    per contract)
        │                                                │
        │                                                ▼
        │                                       GEX Compute Engine
        │                                   (per-strike, total, walls,
        │                                    flip-curve via own BS)
        │                                                │
        │                          ┌─────────────────────┤
        │                          ▼                     ▼
        │                  Postgres Writer       (later) FastAPI + WebSocket
        │                  (reference, OI,                     │
        │                   gex snapshots)                     ▼
        │                                              (later) React Dashboard
        └─ reconnect / re-subscribe on disconnect
```

**Components:**
- **ib_async session** — async connection to Gateway; the actively maintained successor to `ib_insync`.
- **Subscription Manager** — *the* IP-bearing component: owns the line budget, schedules tiers, runs throttled snapshot rotation, handles re-windowing and re-subscribe.
- **Tick Handlers** — route `tickOptionComputation` (greeks/IV), OI ticks, and underlying spot into the state store.
- **In-Memory Market State** — latest value per contract; single read surface for the compute engine.
- **GEX Compute Engine** — pure-ish, fixture-testable offline; broker greeks for "now," own BS for the flip curve.
- **Postgres Writer** — persists reference data, daily OI, and computed GEX snapshots (not raw tick spam).
- **API tier (later)** — FastAPI + WebSocket push to React.

---

## 8. Data Model (entities & cadence — not DDL)

| Entity | Key fields | Cadence / notes |
|--------|------------|-----------------|
| `contracts` | conId, symbol, expiry, strike, right, multiplier, trading_class, exchange | Reference data; refreshed on chain discovery (daily / on demand) |
| `oi_daily` | conId, session_date, open_interest | One row per contract per trading day (D3) |
| `greeks_snapshots` | ts, conId, gamma, delta, vega, theta, iv, opt_price, und_price, source(`stream`/`snapshot`), tick_type(`model`/`bid`/`ask`) | Persist NTM at coarse cadence (e.g., every recompute or every N s); avoid full tick persistence |
| `gex_snapshots` | ts, underlying, spot, total_gex, zero_gamma_level, call_wall, put_wall, profile (JSON: strike→gex), regime | Written each recompute; powers history/replay |
| `runs` | run_id, started_at, ended_at, line_cap, config_hash | Session/run metadata for reproducibility |

**Storage notes:** partition time-series tables by **day**; define retention (e.g., keep N days of snapshots, archive/drop older). Native Postgres is sufficient for v1; TimescaleDB is an optional later optimization, not a v1 dependency. Keep it pragmatic — no premature partitioning machinery.

---

## 9. Operational Lifecycle

- **Session scheduler** — start acquisition at market open, stop at close; do not burn lines/compute overnight. Respect SPX options trading hours (incl. any extended session in scope).
- **Connection management** — auto-reconnect on disconnect, then **re-subscribe** the full tier set and re-fetch OI if stale.
- **Daily Gateway restart** — IBC handles the daily logout/re-auth; the service detects reconnection and rehydrates.
- **Pacing safety** — keep request rate under the ~50/s ceiling; queue/throttle snapshot batches; remember the **three-violation disconnect** rule. Prefer fewer, steady requests.
- **NaN / stale greeks** — illiquid strikes can return NaN or stale model greeks; fall back to own BS or clip strikes with no usable IV.
- **Startup OI fetch** — pull OI once at session start (or after settlement) and cache; do not re-poll intraday.

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OI (generic tick 101 / `callOpenInterest`/`putOpenInterest`) may not populate reliably for **index** options via API | Medium | High | **Validate in M2** explicitly; if unreliable, derive OI from a daily file/source and cache, or fall back to volume-weighted approximation flagged as such |
| `snapshot=True` may not reliably return **modelGreeks** | Medium | High | **Validate in M2**; if unreliable, use *brief-stream-then-cancel* for Tier-2/3 instead of true snapshots |
| Market-data-line exhaustion → silent data loss + pacing disconnects | Medium | High | Centralized budget owner (D8); hard assertions that active lines ≤ cap; tier caps enforced |
| Pacing violations → session termination | Medium | High | Throttle/queue requests; steady cadence; never burst the rotation |
| Gateway daily logout breaks unattended runs | High | Medium | IBC auto-restart (D6); reconnect + rehydrate logic |
| NaN/stale greeks on illiquid wings distort GEX | Medium | Medium | Own-BS fallback; clip strikes lacking IV; wings contribute little anyway |
| **GEX sign/convention error** silently inverts the signal | Low | High | Reference cross-check in M8; explicit sign documentation in code + dashboard |
| Data entitlement / professional flag → API returns nothing despite TWS showing quotes | Medium | High | **M0 gate**: confirm non-pro status, OPRA + streaming bundle, signed API acknowledgement |
| Sticky-strike assumption misstates flip under vol moves | Low | Medium | Documented (D7); isolated so a surface-shift can replace it later |
| Far-expiry / wing gamma staleness | Low | Low | Acceptable by design; Tier-3 low frequency; impact on near-term dealer gamma is minor |

---

## 11. Validation Strategy

- **Reference cross-check** — qualitatively compare computed total-GEX sign, profile shape, and flip level against a public GEX reference for the same session/day. We are matching **shape and regime**, not someone else's exact scalar.
- **Broker-vs-own-BS gamma reconciliation** — for a handful of NTM strikes, our BS gamma should closely track IBKR's streamed gamma; large divergence signals an IV/time/rate input bug.
- **OI sanity** — total OI and per-strike magnitudes within plausible bounds; no all-zero/NaN columns silently feeding GEX.
- **Line-budget assertion** — instrument the subscription manager; assert active lines never exceed the cap across a full session.
- **Replay test** — record a session's tick/snapshot stream; replay it deterministically through the compute engine to validate outputs and catch regressions.
- **Full-session soak** — run open-to-close (incl. a daily Gateway restart) and confirm no leaks, no pacing disconnects, stable recompute cadence.

---

## 12. Phasing (maps to `TODO.md` macros)

| Macro | Intent | Exit criterion |
|-------|--------|----------------|
| **M0 — Environment, entitlements & connectivity** | Gateway + IBC + data subscriptions + `ib_async`; prove a live quote arrives via API | A live SPY/SPX quote + one option's model greeks received over the API |
| **M1 — Contract universe & chain discovery** | `reqSecDefOptParams`; expiry/strike selection; cache contracts | Front-expiry NTM contract set built, qualified, and persisted |
| **M2 — Acquisition feasibility spike (HARD GATE)** | Validate greeks-via-stream, **OI tick for index options**, **snapshot-greeks reliability**, NaN behavior, line counting | Documented yes/no on each unknown; acquisition approach locked |
| **M3 — Line-budget & subscription manager** | Budget owner, tier scheduler, snapshot rotation, re-windowing, in-memory state | Tiers run within budget; recenter works; assertion holds over a session |
| **M4 — GEX computation engine** | Per-strike, total, walls, flip-curve via own BS; conventions | Engine reproduces fixtures; flip curve validated vs manual calc |
| **M5 — Persistence layer (Postgres)** | Schema, daily OI cache, snapshot writers, retention | Snapshots persist + reload; OI cached once/day; retention enforced |
| **M6 — Orchestration & lifecycle** | Scheduler, reconnect/re-subscribe, IBC integration, pacing safety | Survives a forced disconnect and a daily Gateway restart, unattended |
| **M7 — API & delivery contract** | Design (not build) FastAPI + WebSocket payload/contract | Reviewed, frozen API + WS schema doc; **no implementation** |
| **M8 — Validation, reconciliation & hardening** | Reference cross-check, replay, soak, assertions | All §11 checks pass; one clean open-to-close soak |
| **M9 — Frontend dashboard (later)** | React profile/flip/walls views over the WS feed | Live dashboard renders profile, flip level, walls; deferred |

---

## 13. Working Conventions

- **Plan-first / verify-before-build:** confirm this plan and `TODO.md` before any implementation. **M2 is a hard gate** — do not commit the acquisition architecture until its unknowns are validated.
- **Capture lessons:** record any correction or surprising IBKR behavior in `tasks/lessons.md` with a rule that prevents recurrence (especially M2 findings).
- **Elegance check** on non-trivial components (subscription manager, compute engine): pause and ask whether there is a simpler structure before finalizing.
- **Simplicity / minimal impact:** smallest change that proves the next step; no speculative generality (e.g., no multi-underlying machinery in v1).
