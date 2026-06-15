"""The GEX computation engine.

Pure domain logic: takes a consistent snapshot of market inputs and produces a
``GexSnapshot``. No FastAPI, no ib_async, no IO — so it is trivially unit- and
replay-testable. The dealer-position sign convention lives here and nowhere else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.core.models.contracts import OptionContract, OptionRight
from app.core.models.gex import GexLevels, GexSnapshot, Regime, StrikeGex
from app.core.models.market import DataSource, GreeksUpdate
from app.core.models.quality import DataQuality


@dataclass
class EngineInputs:
    """A consistent read of market state at one instant. Internal, not a wire model."""

    underlying: str
    spot: float | None
    now: datetime
    rate: float
    contracts: dict[int, OptionContract] = field(default_factory=dict)
    greeks: dict[int, GreeksUpdate] = field(default_factory=dict)
    oi: dict[int, int] = field(default_factory=dict)


def _dollar_gamma(gamma: float, oi: int, multiplier: int, spot: float) -> float:
    """USD gamma per 1% spot move."""
    return gamma * oi * multiplier * spot * spot * 0.01


@dataclass
class _StrikeAcc:
    call_gex: float = 0.0
    put_gex: float = 0.0
    call_oi: int = 0
    put_oi: int = 0
    good_legs: int = 0
    total_legs: int = 0


class GexEngine:
    def compute(
        self,
        inputs: EngineInputs,
        quality: DataQuality,
        zero_gamma: float | None,
    ) -> GexSnapshot:
        spot = inputs.spot
        if spot is None or spot <= 0:
            raise ValueError("GexEngine.compute requires a positive spot")

        acc: dict[float, _StrikeAcc] = {}
        expiries: set[date] = set()

        for con_id, contract in inputs.contracts.items():
            strike_acc = acc.setdefault(contract.strike, _StrikeAcc())
            strike_acc.total_legs += 1

            g = inputs.greeks.get(con_id)
            o = inputs.oi.get(con_id)
            if g is None or g.gamma is None or o is None:
                continue  # unusable leg; still counted in total_legs for quality

            dollar = _dollar_gamma(g.gamma, o, contract.multiplier, spot)
            if contract.right is OptionRight.CALL:
                strike_acc.call_gex += dollar
                strike_acc.call_oi += o
            else:
                strike_acc.put_gex -= dollar  # dealer short-put assumption
                strike_acc.put_oi += o

            if g.source is not DataSource.BS_FALLBACK:
                strike_acc.good_legs += 1
            expiries.add(contract.expiry)

        profile: list[StrikeGex] = []
        for strike in sorted(acc):
            a = acc[strike]
            q = (a.good_legs / a.total_legs) if a.total_legs else 0.0
            profile.append(
                StrikeGex(
                    strike=strike,
                    call_gex=a.call_gex,
                    put_gex=a.put_gex,
                    net_gex=a.call_gex + a.put_gex,
                    call_oi=a.call_oi,
                    put_oi=a.put_oi,
                    quality=q,
                )
            )

        call_total = sum(s.call_gex for s in profile)
        put_total = sum(s.put_gex for s in profile)          # <= 0
        net = call_total + put_total
        gross = call_total + abs(put_total)
        ratio = (call_total / abs(put_total)) if put_total != 0 else None

        call_oi_total = sum(s.call_oi for s in profile)
        put_oi_total = sum(s.put_oi for s in profile)

        levels = self._levels(profile, spot, zero_gamma)
        regime = self._regime(net, quality)

        return GexSnapshot(
            ts=inputs.now,
            underlying=inputs.underlying,
            spot=spot,
            net_gex=net,
            gross_gex=gross,
            call_gex_total=call_total,
            put_gex_total=put_total,
            gex_ratio=ratio,
            call_oi_total=call_oi_total,
            put_oi_total=put_oi_total,
            total_oi=call_oi_total + put_oi_total,
            regime=regime,
            levels=levels,
            profile=profile,
            expiries_included=sorted(expiries),
            quality=quality,
        )

    @staticmethod
    def _levels(profile: list[StrikeGex], spot: float, zero_gamma: float | None) -> GexLevels:
        call_bars = [s for s in profile if s.call_gex > 0]
        put_bars = [s for s in profile if s.put_gex < 0]
        call_wall = max(call_bars, key=lambda s: s.call_gex).strike if call_bars else None
        put_wall = min(put_bars, key=lambda s: s.put_gex).strike if put_bars else None
        return GexLevels(
            zero_gamma=zero_gamma,
            call_wall=call_wall,
            put_wall=put_wall,
            call_wall_dist_pct=(call_wall / spot - 1.0) * 100.0 if call_wall else None,
            put_wall_dist_pct=(put_wall / spot - 1.0) * 100.0 if put_wall else None,
        )

    @staticmethod
    def _regime(net: float, quality: DataQuality) -> Regime:
        if quality.t1_coverage < 0.10 or net == 0:
            return Regime.UNKNOWN
        return Regime.LONG_GAMMA if net > 0 else Regime.SHORT_GAMMA
