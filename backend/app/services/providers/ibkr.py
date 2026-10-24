"""IBKR market-data provider (ib_async).

Implements the Tier-1 path from PLAN.md: connect to a running IB Gateway/TWS,
discover the option chain, stream near-the-money greeks, and fetch open interest
once. Normalizes every tick into the same Pydantic models the simulator emits,
so nothing downstream changes between providers.

STATUS — M2 HARD GATE (see PLAN.md / TODO.md): this path requires a live
Gateway and the two IBKR unknowns to be validated empirically before it can be
trusted (does OI tick 101 populate for INDEX options; do snapshot greeks
arrive reliably). It is written to be correct-by-construction but is NOT
verified against a live feed here.

Deliberately out of scope of this file (later milestones):
  - Tier-2/3 rotation + the rotating snapshot pool (M3)
  - NTM re-windowing on spot drift (M3)
  - reconnect / re-subscribe + IBC daily-restart recovery (M6)
The ``import ib_async`` is guarded so the service runs in 'simulated' mode even
when ib_async is not installed.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

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
from app.services.providers.base import MarketDataProvider, MarketSink, ProviderHealth

try:  # ib_async is optional; only required when provider == "ibkr"
    from ib_async import IB, Future, Index, Option, Ticker
except Exception:  # pragma: no cover - import guard
    IB = None  # type: ignore[assignment]

log = logging.getLogger("gex.ibkr")


class IBKRProvider(MarketDataProvider):
    def __init__(self, settings: Settings, sink: MarketSink) -> None:
        if IB is None:
            raise RuntimeError(
                "provider='ibkr' requires the 'ib_async' package and a running IB Gateway/TWS."
            )
        self._s = settings
        self._sink = sink
        self._ib = IB()
        self._tickers: dict[int, "Ticker"] = {}
        self._oi_seen: set[int] = set()
        self._connected = False

    async def start(self) -> None:
        try:
            await self._ib.connectAsync(
                self._s.ibkr_host, self._s.ibkr_port, clientId=self._s.ibkr_client_id
            )
        except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as e:
            raise RuntimeError(
                f"cannot reach TWS/Gateway at {self._s.ibkr_host}:{self._s.ibkr_port}. "
                "Start TWS, enable Global Configuration > API > Settings > "
                "'Enable ActiveX and Socket Clients', and match GEX_IBKR_PORT "
                "(TWS paper 7497, Gateway paper 4002)."
            ) from e
        self._connected = True

        underlying = await self._qualify_underlying()
        und_ticker = self._ib.reqMktData(underlying, "", False, False)
        und_ticker.updateEvent += self._make_quote_handler(self._s.underlying)
        spot = await self._await_spot(und_ticker)

        contracts = await self._discover_ntm(underlying, spot)
        self._assert_budget(len(contracts))

        es = await self._qualify_es()
        if es is not None:
            es_ticker = self._ib.reqMktData(es, "", False, False)
            es_ticker.updateEvent += self._make_quote_handler("ES")
            self._tickers[es.conId] = es_ticker  # counted in health(), cancelled in stop()

        for contract, ib_opt in contracts:
            self._sink.register_contract(contract)
            # genericTickList "101" enables option open interest
            ticker = self._ib.reqMktData(ib_opt, "101", False, False)
            ticker.updateEvent += self._make_option_handler(contract)
            self._tickers[contract.con_id] = ticker

    async def stop(self) -> None:
        self._connected = False
        for ticker in self._tickers.values():
            try:
                self._ib.cancelMktData(ticker.contract)
            except Exception:
                pass
        if self._ib.isConnected():
            self._ib.disconnect()

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            connected=self._connected and self._ib.isConnected(),
            lines_in_use=len(self._tickers) + 1,  # +1 for the underlying
        )

    # --- discovery ---------------------------------------------------------
    async def _qualify_underlying(self):
        index = Index(self._s.underlying, "CBOE")
        (qualified,) = await self._ib.qualifyContractsAsync(index)
        return qualified

    async def _qualify_es(self):
        """The ES future most traders hold: nearest expiry more than 8 days out.

        shortcut: 8 days approximates the CME roll date; during roll week check
        that TWS shows the same contract. Returns None (basis shows N/A) rather
        than failing GEX when ES is unavailable.
        """
        details = await self._ib.reqContractDetailsAsync(Future("ES", exchange="CME"))
        cutoff = (date.today() + timedelta(days=8)).strftime("%Y%m%d")
        futures = sorted(
            (d.contract for d in details if d.contract.lastTradeDateOrContractMonth[:8] > cutoff),
            key=lambda c: c.lastTradeDateOrContractMonth,
        )
        if not futures:
            log.warning("no ES future found; ES basis disabled (check CME permissions)")
            return None
        return futures[0]

    async def _discover_ntm(self, underlying, spot: float) -> list[tuple[OptionContract, object]]:
        """Front expiry, NTM +/- N strikes, both rights. Returns (model, ib_contract)."""
        params = await self._ib.reqSecDefOptParamsAsync(
            underlying.symbol, "", underlying.secType, underlying.conId
        )
        # SPX has two SMART chains (SPX monthlies, SPXW dailies); the front expiry lives in SPXW
        smart = [p for p in params if p.exchange == "SMART"] or params
        chain = min(smart, key=lambda p: min(p.expirations))
        expiry = min(chain.expirations)

        n, spacing = self._s.ntm_strikes_each_side, self._s.strike_spacing
        center = round(spot / spacing) * spacing
        wanted = {center + i * spacing for i in range(-n, n + 1)}
        strikes = sorted(s for s in chain.strikes if s in wanted)

        ib_options = [
            Option(underlying.symbol, expiry, strike, right, "SMART", tradingClass=chain.tradingClass)
            for strike in strikes
            for right in ("C", "P")
        ]
        qualified = await self._ib.qualifyContractsAsync(*ib_options)

        out: list[tuple[OptionContract, object]] = []
        for ib_opt in qualified:
            if ib_opt is None:
                continue  # strike not listed for this expiry; ib_async already logged it
            out.append(
                (
                    OptionContract(
                        con_id=ib_opt.conId,
                        symbol=ib_opt.symbol,
                        trading_class=ib_opt.tradingClass,
                        expiry=date.fromisoformat(_ib_date(ib_opt.lastTradeDateOrContractMonth)),
                        strike=float(ib_opt.strike),
                        right=OptionRight(ib_opt.right),
                        multiplier=int(ib_opt.multiplier or 100),
                    ),
                    ib_opt,
                )
            )
        return out

    async def _await_spot(self, ticker: "Ticker", timeout: float = 5.0) -> float:
        """First valid price from the already-subscribed underlying ticker.

        Raises instead of guessing: a wrong spot centers the NTM window on the
        wrong strikes and every downstream number is silently garbage.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            price = ticker.marketPrice()
            if price and price == price:  # not NaN
                return float(price)
            await asyncio.sleep(0.2)
        raise RuntimeError(
            f"no {self._s.underlying} price within {timeout}s; "
            "check the CBOE index market-data subscription; a paper account also needs "
            "'share real-time market data' enabled from the live account in Client Portal"
        )

    def _assert_budget(self, n_options: int) -> None:
        needed = n_options + 2  # + underlying + ES future
        budget = self._s.line_cap - self._s.line_reserve
        if needed > budget:
            raise RuntimeError(
                f"line budget exceeded: need {needed} lines, budget is {budget} "
                f"(cap {self._s.line_cap} - reserve {self._s.line_reserve}). "
                f"Reduce ntm_strikes_each_side or add Quote Booster lines."
            )

    # --- tick handlers -----------------------------------------------------
    def _make_quote_handler(self, symbol: str):
        def handler(ticker: "Ticker") -> None:
            self._sink.on_quote(
                UnderlyingQuote(
                    symbol=symbol,
                    ts=utcnow(),
                    last=ticker.last,
                    bid=ticker.bid,
                    ask=ticker.ask,
                )
            )

        return handler

    def _make_option_handler(self, contract: OptionContract):
        def handler(ticker: "Ticker") -> None:
            mg = ticker.modelGreeks
            if mg is not None:
                self._sink.on_greeks(
                    GreeksUpdate(
                        con_id=contract.con_id,
                        ts=utcnow(),
                        basis=GreeksBasis.MODEL,
                        source=DataSource.STREAM,
                        iv=mg.impliedVol,
                        delta=mg.delta,
                        gamma=mg.gamma,
                        vega=mg.vega,
                        theta=mg.theta,
                        opt_price=mg.optPrice,
                        und_price=mg.undPrice,
                    )
                )
            self._maybe_emit_oi(contract, ticker)

        return handler

    def _maybe_emit_oi(self, contract: OptionContract, ticker: "Ticker") -> None:
        if contract.con_id in self._oi_seen:
            return  # OI is end-of-day data; emit once
        oi = ticker.callOpenInterest if contract.right is OptionRight.CALL else ticker.putOpenInterest
        if oi is None or oi != oi or oi < 0:  # None / NaN / invalid
            return
        self._oi_seen.add(contract.con_id)
        self._sink.on_oi(
            OpenInterestRecord(
                con_id=contract.con_id,
                session_date=date.today(),
                open_interest=int(oi),
                fetched_at=utcnow(),
            )
        )


def _ib_date(value: str) -> str:
    """IBKR dates come as 'YYYYMMDD' (or sometimes 'YYYYMM'). Normalize to ISO."""
    v = value[:8]
    return f"{v[0:4]}-{v[4:6]}-{v[6:8]}"
