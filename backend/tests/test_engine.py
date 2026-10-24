"""Unit tests for the GEX math: dealer sign convention, walls, zero gamma,
time to expiry, and greek freshness. Hand-built inputs, no IO."""
from __future__ import annotations

import asyncio
import math
from datetime import date, datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.core.models.contracts import OptionContract, OptionRight
from app.core.models.gex import Regime
from app.core.models.market import DataSource, GreeksBasis, GreeksUpdate
from app.core.models.quality import DataQuality, FeedStatus
from app.services.gex.black_scholes import bs_delta, bs_gamma, year_fraction
from app.services.gex.engine import EngineInputs, GexEngine
from app.services.gex.flip import compute_flip_curve
from app.services.state import MarketState

NOW = datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)  # 10:00 New York
EXPIRY = date(2026, 10, 23)
SPOT = 6000.0
IV = 0.18


def _leg(con_id: int, strike: float, right: OptionRight, ts: datetime = NOW):
    contract = OptionContract(
        con_id=con_id, symbol="SPX", trading_class="SPXW",
        expiry=EXPIRY, strike=strike, right=right,
    )
    gamma = bs_gamma(SPOT, strike, year_fraction(EXPIRY, NOW), 0.04, IV)
    greeks = GreeksUpdate(
        con_id=con_id, ts=ts, basis=GreeksBasis.MODEL, source=DataSource.STREAM,
        iv=IV, gamma=gamma,
    )
    return contract, greeks


def _inputs() -> EngineInputs:
    # put-heavy below spot, call-heavy above: the classic negative-below / positive-above profile
    legs = [
        (_leg(1, 5900.0, OptionRight.PUT), 5000),
        (_leg(2, 5950.0, OptionRight.PUT), 2000),
        (_leg(3, 6050.0, OptionRight.CALL), 2000),
        (_leg(4, 6100.0, OptionRight.CALL), 5000),
    ]
    return EngineInputs(
        underlying="SPX", spot=SPOT, now=NOW, rate=0.04,
        contracts={c.con_id: c for (c, _), _ in legs},
        greeks={g.con_id: g for (_, g), _ in legs},
        oi={c.con_id: oi for (c, _), oi in legs},
    )


def test_engine_signs_walls_and_totals():
    quality = DataQuality(status=FeedStatus.LIVE, t1_coverage=1.0)
    snap = GexEngine().compute(_inputs(), quality=quality, zero_gamma=None)

    by_strike = {s.strike: s for s in snap.profile}
    assert by_strike[5900.0].put_gex < 0 and by_strike[5900.0].call_gex == 0
    assert by_strike[6100.0].call_gex > 0 and by_strike[6100.0].put_gex == 0
    assert snap.put_gex_total < 0 < snap.call_gex_total
    assert snap.net_gex == pytest.approx(snap.call_gex_total + snap.put_gex_total)
    assert snap.gross_gex == pytest.approx(snap.call_gex_total - snap.put_gex_total)
    assert snap.levels.call_wall == 6100.0
    assert snap.levels.put_wall == 5900.0
    assert snap.levels.put_wall_dist_pct == pytest.approx((5900 / SPOT - 1) * 100)
    assert snap.regime in (Regime.LONG_GAMMA, Regime.SHORT_GAMMA)


def test_flip_zero_crossing_lies_between_put_and_call_walls():
    flip = compute_flip_curve(_inputs(), grid_points=81, grid_span=0.10)
    assert flip.points[0].net_gex < 0 < flip.points[-1].net_gex
    assert flip.zero_crossing is not None
    assert 5900.0 < flip.zero_crossing < 6100.0


def test_year_fraction_uses_new_york_close():
    one_hour = 1 / (365 * 24)
    # 15:00 New York (EDT, UTC-4) on expiry day -> one hour left, not half a day
    assert year_fraction(date(2026, 10, 16), datetime(2026, 10, 16, 19, 0, tzinfo=timezone.utc)) == (
        pytest.approx(one_hour)
    )
    # after the close: floored, positive, finite
    after = year_fraction(date(2026, 10, 16), datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc))
    assert 0 < after < one_hour and math.isfinite(bs_gamma(SPOT, SPOT, after, 0.04, IV))


def test_stale_greeks_do_not_count_as_fresh():
    state = MarketState("SPX")
    fresh_c, fresh_g = _leg(1, 6000.0, OptionRight.CALL, ts=NOW)
    old_c, old_g = _leg(2, 6000.0, OptionRight.PUT, ts=NOW - timedelta(minutes=5))
    for c, g in ((fresh_c, fresh_g), (old_c, old_g)):
        state.register_contract(c)
        state.on_greeks(g)
    assert state.fresh_greeks_count(NOW, max_age_s=10.0) == 1


def test_ibkr_await_spot_raises_instead_of_guessing():
    pytest.importorskip("ib_async")
    from app.services.providers.ibkr import IBKRProvider

    class _Ticker:
        def __init__(self, price: float) -> None:
            self._price = price

        def marketPrice(self) -> float:
            return self._price

    provider = IBKRProvider(Settings(), MarketState("SPX"))
    assert asyncio.run(provider._await_spot(_Ticker(6712.5), timeout=0.5)) == 6712.5
    with pytest.raises(RuntimeError, match="no SPX price"):
        asyncio.run(provider._await_spot(_Ticker(float("nan")), timeout=0.3))


def test_ibkr_discover_picks_spxw_front_and_skips_unlisted():
    pytest.importorskip("ib_async")
    from types import SimpleNamespace as NS
    from app.services.providers.ibkr import IBKRProvider

    strikes = [5995.0, 6000.0, 6005.0]
    chains = [  # monthly chain listed first: the old code picked it
        NS(exchange="SMART", tradingClass="SPX", expirations=["20261120"], strikes=strikes),
        NS(exchange="SMART", tradingClass="SPXW", expirations=["20261020", "20261019"], strikes=strikes),
    ]

    class _FakeIB:
        async def reqSecDefOptParamsAsync(self, *_):
            return chains

        async def qualifyContractsAsync(self, *opts):
            for i, o in enumerate(opts, 1):
                o.conId, o.multiplier = i, "100"
            return [None if o.strike == 6005.0 else o for o in opts]  # 6005 unlisted

    provider = IBKRProvider(Settings(ntm_strikes_each_side=1), MarketState("SPX"))
    provider._ib = _FakeIB()
    got = asyncio.run(provider._discover_ntm(NS(symbol="SPX", secType="IND", conId=1), 6001.0))
    assert {c.trading_class for c, _ in got} == {"SPXW"}
    assert {c.expiry for c, _ in got} == {date(2026, 10, 19)}
    assert sorted(c.strike for c, _ in got) == [5995.0, 5995.0, 6000.0, 6000.0]


def test_net_dex_natural_delta_sign():
    inputs = _inputs()
    deltas = {1: -0.1, 2: -0.4, 3: 0.4, 4: 0.3}
    inputs.greeks = {k: g.model_copy(update={"delta": deltas[k]}) for k, g in inputs.greeks.items()}
    snap = GexEngine().compute(
        inputs, quality=DataQuality(status=FeedStatus.LIVE, t1_coverage=1.0), zero_gamma=None
    )
    # -0.1*5000 - 0.4*2000 + 0.4*2000 + 0.3*5000 = 1000 delta-contracts
    assert snap.net_dex == pytest.approx(1000 * 100 * SPOT)


def test_es_basis_fresh_and_stale():
    from app.core.models.market import UnderlyingQuote

    state = MarketState("SPX")
    state.on_quote(UnderlyingQuote(symbol="SPX", ts=NOW, bid=5999.9, ask=6000.1))
    state.on_quote(UnderlyingQuote(symbol="ES", ts=NOW, bid=6035.0, ask=6035.5))
    assert state.resolved_spot() == pytest.approx(6000.0)  # ES must not overwrite spot

    fresh = state.snapshot_inputs(NOW + timedelta(seconds=5), 0.04, es_max_age_s=10)
    stale = state.snapshot_inputs(NOW + timedelta(seconds=30), 0.04, es_max_age_s=10)
    quality = DataQuality(status=FeedStatus.LIVE, t1_coverage=1.0)
    for inputs in (fresh, stale):
        base = _inputs()
        inputs.contracts, inputs.greeks, inputs.oi = base.contracts, base.greeks, base.oi
    assert GexEngine().compute(fresh, quality, None).es_basis == pytest.approx(35.25)
    assert GexEngine().compute(stale, quality, None).es_basis is None


def test_bs_delta_put_call_parity():
    t = year_fraction(EXPIRY, NOW)
    call = bs_delta(SPOT, 6050.0, t, 0.04, IV, is_call=True)
    put = bs_delta(SPOT, 6050.0, t, 0.04, IV, is_call=False)
    assert 0 < call < 1 and call - put == pytest.approx(1.0)
