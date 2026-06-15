"""Zero-gamma (flip) computation.

Naively scaling current per-strike gamma by spot**2 is wrong, because gamma
itself moves with spot. So we re-evaluate each option's Black-Scholes gamma
across a grid of hypothetical spot levels (holding each strike's IV fixed —
sticky-strike, PLAN.md D7), sum the net dealer GEX at each, and locate the
zero crossing nearest the current spot.
"""
from __future__ import annotations

from datetime import date

from app.core.models.contracts import OptionRight
from app.core.models.gex import FlipCurve, FlipCurvePoint
from app.services.gex.black_scholes import bs_gamma
from app.services.gex.engine import EngineInputs

_MIN_T_YEARS = 0.5 / 365.0  # floor so 0DTE gamma stays finite


def _year_fraction(expiry: date, today: date) -> float:
    days = (expiry - today).days
    return max(days, 0) / 365.0 or _MIN_T_YEARS


def compute_flip_curve(inputs: EngineInputs, grid_points: int, grid_span: float) -> FlipCurve:
    spot = inputs.spot
    if spot is None or spot <= 0 or grid_points < 2:
        return FlipCurve(ts=inputs.now, points=[], zero_crossing=None)

    today = inputs.now.date()
    lo, hi = spot * (1 - grid_span), spot * (1 + grid_span)
    step = (hi - lo) / (grid_points - 1)

    points: list[FlipCurvePoint] = []
    for i in range(grid_points):
        s = lo + i * step
        net = 0.0
        for con_id, contract in inputs.contracts.items():
            g = inputs.greeks.get(con_id)
            o = inputs.oi.get(con_id)
            if g is None or g.iv is None or o is None:
                continue
            t = _year_fraction(contract.expiry, today)
            gamma = bs_gamma(s, contract.strike, t, inputs.rate, g.iv)
            dollar = gamma * o * contract.multiplier * s * s * 0.01
            net += dollar if contract.right is OptionRight.CALL else -dollar
        points.append(FlipCurvePoint(spot=s, net_gex=net))

    return FlipCurve(ts=inputs.now, points=points, zero_crossing=_nearest_zero(points, spot))


def _nearest_zero(points: list[FlipCurvePoint], spot: float) -> float | None:
    """Linear-interpolate sign changes; return the crossing nearest current spot."""
    crossings: list[float] = []
    for a, b in zip(points, points[1:]):
        if a.net_gex == 0.0:
            crossings.append(a.spot)
        elif (a.net_gex < 0) != (b.net_gex < 0):
            frac = (0.0 - a.net_gex) / (b.net_gex - a.net_gex)
            crossings.append(a.spot + frac * (b.spot - a.spot))
    if not crossings:
        return None
    return min(crossings, key=lambda x: abs(x - spot))
