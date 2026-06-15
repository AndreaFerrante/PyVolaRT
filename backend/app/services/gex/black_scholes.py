"""Black-Scholes gamma. Used for the flip-curve sweep (re-pricing gamma at
hypothetical spot levels) and as a fallback when broker greeks are unusable.

Plain `math` only — no numpy/scipy — to keep the dependency surface small and
the logic obvious.
"""
from __future__ import annotations

import math

_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)


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
