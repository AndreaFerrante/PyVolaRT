"""Black-Scholes gamma. Used for the flip-curve sweep (re-pricing gamma at
hypothetical spot levels) and as a fallback when broker greeks are unusable.

Plain `math` only — no numpy/scipy — to keep the dependency surface small and
the logic obvious.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)

_EXPIRY_CLOSE = time(16, 0, tzinfo=ZoneInfo("America/New_York"))
_SECONDS_PER_YEAR = 365.0 * 24 * 3600
_MIN_T_YEARS = 15 * 60 / _SECONDS_PER_YEAR  # floor so gamma stays finite at/after the close


def year_fraction(expiry: date, now: datetime) -> float:
    """Calendar time from ``now`` (aware) to the 16:00 New York close on ``expiry``.

    shortcut: assumes PM settlement (SPXW); AM-settled SPX monthlies stop
    trading the day before, so their T is overstated by up to a day.
    """
    seconds = (datetime.combine(expiry, _EXPIRY_CLOSE) - now).total_seconds()
    return max(seconds / _SECONDS_PER_YEAR, _MIN_T_YEARS)


def norm_pdf(x: float) -> float:
    return _INV_SQRT_2PI * math.exp(-0.5 * x * x)


def bs_gamma(spot: float, strike: float, t_years: float, rate: float, sigma: float) -> float:
    """Black-Scholes gamma. Returns 0.0 for degenerate inputs rather than raising.

    Gamma is identical for a call and a put at the same strike (put-call symmetry);
    callers apply the dealer-position sign, not this function.
    """
    if spot <= 0 or strike <= 0 or t_years <= 0 or sigma <= 0:
        return 0.0
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    return norm_pdf(d1) / (spot * sigma * sqrt_t)
