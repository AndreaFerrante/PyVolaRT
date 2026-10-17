"""In-memory market state.

A flat, ``con_id``-keyed latest-value store. It is also the ``MarketSink`` the
provider writes into, and it tracks a single dirty flag so the recompute loop
knows when there is new data to act on. Single asyncio event loop, so plain
synchronous mutation is safe (no locks needed).
"""
from __future__ import annotations

from datetime import date, datetime

from app.core.models.contracts import OptionContract
from app.core.models.market import GreeksUpdate, OpenInterestRecord, UnderlyingQuote
from app.services.gex.engine import EngineInputs


class MarketState:
    def __init__(self, underlying: str) -> None:
        self.underlying = underlying
        self._contracts: dict[int, OptionContract] = {}
        self._greeks: dict[int, GreeksUpdate] = {}
        self._oi: dict[int, int] = {}
        self._oi_session_date: date | None = None
        self._quote: UnderlyingQuote | None = None
        self._dirty = False

    # --- MarketSink surface ------------------------------------------------
    def register_contract(self, contract: OptionContract) -> None:
        self._contracts[contract.con_id] = contract

    def on_greeks(self, update: GreeksUpdate) -> None:
        self._greeks[update.con_id] = update
        self._dirty = True

    def on_quote(self, quote: UnderlyingQuote) -> None:
        self._quote = quote
        self._dirty = True

    def on_oi(self, record: OpenInterestRecord) -> None:
        self._oi[record.con_id] = record.open_interest
        self._oi_session_date = record.session_date
        self._dirty = True

    # --- read surface ------------------------------------------------------
    def consume_dirty(self) -> bool:
        was = self._dirty
        self._dirty = False
        return was

    def resolved_spot(self) -> float | None:
        return self._quote.spot if self._quote else None

    def spot_age_s(self, now: datetime) -> float | None:
        if self._quote is None:
            return None
        return (now - self._quote.ts).total_seconds()

    def oi_session_date(self) -> date | None:
        return self._oi_session_date

    def contract_count(self) -> int:
        return len(self._contracts)

    def fresh_greeks_count(self, now: datetime, max_age_s: float) -> int:
        return sum(
            1
            for g in self._greeks.values()
            if g.gamma is not None and (now - g.ts).total_seconds() <= max_age_s
        )

    def snapshot_inputs(self, now: datetime, rate: float) -> EngineInputs:
        """Consistent copy of inputs for one compute cycle."""
        return EngineInputs(
            underlying=self.underlying,
            spot=self.resolved_spot(),
            now=now,
            rate=rate,
            contracts=dict(self._contracts),
            greeks=dict(self._greeks),
            oi=dict(self._oi),
        )
