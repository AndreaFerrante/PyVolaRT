"""Computed models — the products served to the frontend and external service.

Units are pinned once here: every GEX value is **USD gamma per 1% spot move**
(``gamma * OI * multiplier * spot**2 * 0.01``). Formatting ($B / $M / %) is a
frontend concern. Sign convention (PLAN.md §6): option gamma is always >= 0;
the put leg is SUBTRACTED under the dealer long-call / short-put assumption, so
``put_gex`` is <= 0 everywhere.
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import AwareDatetime, BaseModel

from app.core.models.quality import DataQuality


class Regime(str, Enum):
    LONG_GAMMA = "long_gamma"    # net > 0 -> dealers suppress volatility
    SHORT_GAMMA = "short_gamma"  # net < 0 -> dealers amplify volatility
    UNKNOWN = "unknown"          # insufficient data quality


class StrikeGex(BaseModel):
    """One bar of the Strike Profile chart."""

    strike: float
    call_gex: float   # >= 0
    put_gex: float    # <= 0
    net_gex: float     # call_gex + put_gex
    call_oi: int
    put_oi: int
    quality: float     # 0-1: share of legs that were fresh & broker-sourced


class GexLevels(BaseModel):
    zero_gamma: float | None = None       # None -> dashboard shows "N/A"
    call_wall: float | None = None        # strike of max positive gamma concentration
    put_wall: float | None = None         # strike of max negative gamma concentration
    call_wall_dist_pct: float | None = None
    put_wall_dist_pct: float | None = None


class GexSnapshot(BaseModel):
    """The primary product. One per recompute."""

    ts: AwareDatetime
    underlying: str
    spot: float

    net_gex: float          # call_total + put_total
    gross_gex: float        # call_total + |put_total|
    call_gex_total: float   # >= 0
    put_gex_total: float    # <= 0
    gex_ratio: float | None = None  # call_total / |put_total|
    # USD delta of open interest: sum(delta * OI * multiplier * spot). Natural delta
    # sign (calls +, puts -), NOT dealer-signed; legs without broker delta are skipped.
    net_dex: float = 0.0
    es_basis: float | None = None  # ES price - SPX spot, in points; None if no fresh ES quote

    call_oi_total: int
    put_oi_total: int
    total_oi: int

    regime: Regime
    levels: GexLevels
    profile: list[StrikeGex]
    expiries_included: list[date]
    quality: DataQuality


class FlipCurvePoint(BaseModel):
    spot: float       # hypothetical S'
    net_gex: float    # net GEX re-priced with own Black-Scholes at S'


class FlipCurve(BaseModel):
    ts: AwareDatetime
    points: list[FlipCurvePoint]
    zero_crossing: float | None = None  # authoritative source of GexLevels.zero_gamma


class LevelsResponse(BaseModel):
    """Lightweight payload for the external service's fast path (`GET /gex/levels`)."""

    ts: AwareDatetime
    underlying: str
    spot: float
    regime: Regime
    levels: GexLevels
    quality: DataQuality
