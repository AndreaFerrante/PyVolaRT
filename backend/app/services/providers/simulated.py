"""Simulated market-data provider.

Generates a coherent, mockup-shaped option universe with no broker connection,
so the whole pipeline (compute -> hub -> WebSocket/REST) runs end-to-end for
frontend work and tests. Gamma is derived from Black-Scholes using a per-strike
IV, so the live GEX profile and the flip-curve sweep agree with each other.

This is NOT a market model — OI/IV shapes are chosen only to look plausible:
put open interest concentrated below spot, calls above, with a put wall and a
call wall, yielding the red-below / green-above profile of the reference design.
"""
from __future__ import annotations

import asyncio
import math
import random
from datetime import date, datetime, timedelta

from app.config import Settings
from app.core.models.contracts import OptionContract, OptionRight
from app.core.models.market import (
    DataSource,
    GreeksBasis,
    GreeksUpdate,
    OpenInterestRecord,
    UnderlyingQuote,
)
from app.core.util import utcnow
from app.services.gex.black_scholes import bs_gamma, year_fraction
from app.services.providers.base import MarketDataProvider, MarketSink, ProviderHealth


class SimulatedProvider(MarketDataProvider):
    def __init__(self, settings: Settings, sink: MarketSink) -> None:
        self._s = settings
        self._sink = sink
        self._contracts: list[OptionContract] = []
        self._oi: dict[int, int] = {}
        self._spot = settings.sim_initial_spot
        self._connected = False
        self._task: asyncio.Task | None = None
        self._rng = random.Random(7)

    async def start(self) -> None:
        self._connected = True
        self._build_universe()
        self._emit_all()  # seed initial state so /current is ready immediately
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._connected = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def health(self) -> ProviderHealth:
        return ProviderHealth(connected=self._connected, lines_in_use=len(self._contracts))

    # --- universe construction --------------------------------------------
    def _build_universe(self) -> None:
        spacing = self._s.strike_spacing
        n = self._s.ntm_strikes_each_side
        center = round(self._s.sim_initial_spot / spacing) * spacing
        expiry = date.today() + timedelta(days=self._s.sim_expiry_days)

        con_id = 1
        for i in range(-n, n + 1):
            strike = center + i * spacing
            for right in (OptionRight.CALL, OptionRight.PUT):
                contract = OptionContract(
                    con_id=con_id,
                    symbol=self._s.underlying,
                    trading_class=self._s.underlying,
                    expiry=expiry,
                    strike=strike,
                    right=right,
                    multiplier=100,
                )
                self._sink.register_contract(contract)
                oi = self._sim_oi(strike, right, center, spacing)
                self._oi[con_id] = oi
                self._sink.on_oi(
                    OpenInterestRecord(
                        con_id=con_id,
                        session_date=date.today(),
                        open_interest=oi,
                        fetched_at=utcnow(),
                    )
                )
                self._contracts.append(contract)
                con_id += 1

    def _sim_oi(self, strike: float, right: OptionRight, center: float, spacing: float) -> int:
        """Plausible OI: a put wall ~8 strikes below, a call wall ~16 above."""
        base = 300
        width = spacing * 10
        d = strike - center
        if right is OptionRight.PUT:
            peak = -spacing * 8
            bump = 1500 * math.exp(-((d - peak) ** 2) / (2 * width * width))
        else:
            peak = spacing * 16
            bump = 1200 * math.exp(-((d - peak) ** 2) / (2 * width * width))
        return int(base + bump)

    # --- emission ----------------------------------------------------------
    def _greek_for(self, contract: OptionContract, spot: float, now: datetime) -> tuple[float, float]:
        t = year_fraction(contract.expiry, now)
        iv = self._s.sim_base_iv + 0.04 * abs(contract.strike - spot) / spot  # simple smile
        gamma = bs_gamma(spot, contract.strike, t, self._s.risk_free_rate, iv)
        return gamma, iv

    def _emit_all(self) -> None:
        now = utcnow()
        self._sink.on_quote(
            UnderlyingQuote(
                symbol=self._s.underlying,
                ts=now,
                last=self._spot,
                bid=self._spot - 0.10,
                ask=self._spot + 0.10,
            )
        )
        for contract in self._contracts:
            gamma, iv = self._greek_for(contract, self._spot, now)
            self._sink.on_greeks(
                GreeksUpdate(
                    con_id=contract.con_id,
                    ts=now,
                    basis=GreeksBasis.MODEL,
                    source=DataSource.STREAM,
                    iv=iv,
                    gamma=gamma,
                    und_price=self._spot,
                )
            )

    async def _run(self) -> None:
        while self._connected:
            await asyncio.sleep(self._s.sim_tick_interval_s)
            # gentle random walk on spot, then re-emit greeks at the new level
            self._spot *= math.exp(self._rng.gauss(0.0, 0.0005))
            self._emit_all()
