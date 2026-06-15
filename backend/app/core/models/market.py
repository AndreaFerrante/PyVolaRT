"""Ingestion models — the normalization layer for the raw IBKR feed.

Raw `ib_async` objects are converted into these at the acquisition boundary.
Critical rule: IBKR sentinels (NaN, inf, UNSET_DOUBLE) become ``None``.
``None`` means "unknown" and is NEVER conflated with ``0`` — zero is a
legitimate market value (e.g. a strike with zero gamma).
"""
from __future__ import annotations

import math
from datetime import date
from enum import Enum

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class GreeksBasis(str, Enum):
    """Which option computation the greeks came from."""

    MODEL = "model"
    BID = "bid"
    ASK = "ask"
    LAST = "last"


class DataSource(str, Enum):
    """Provenance of a datum — lets the engine weigh inputs and flag degradation."""

    STREAM = "stream"            # Tier-1 live tick
    SNAPSHOT = "snapshot"        # Tier-2/3 rotation (or brief-stream-then-cancel)
    BS_FALLBACK = "bs_fallback"  # our own Black-Scholes, used when broker greeks unusable


def _clean(v: object) -> float | None:
    """Map NaN / inf / IBKR's huge UNSET sentinel to None. Sign is preserved
    (negative delta/theta are legitimate, so we do not null on sign)."""
    if v is None:
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f) or abs(f) > 1e100:
        return None
    return f


class GreeksUpdate(BaseModel):
    """One normalized ``tickOptionComputation``."""

    con_id: int
    ts: AwareDatetime
    basis: GreeksBasis
    source: DataSource
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None
    opt_price: float | None = None
    und_price: float | None = None

    @field_validator(
        "iv", "delta", "gamma", "vega", "theta", "opt_price", "und_price",
        mode="before",
    )
    @classmethod
    def _sentinels_to_none(cls, v: object) -> float | None:
        return _clean(v)


class UnderlyingQuote(BaseModel):
    """Spot quote for the underlying. Engine resolves spot as mid(bid,ask) else last."""

    symbol: str
    ts: AwareDatetime
    last: float | None = None
    bid: float | None = None
    ask: float | None = None

    @field_validator("last", "bid", "ask", mode="before")
    @classmethod
    def _sentinels_to_none(cls, v: object) -> float | None:
        return _clean(v)

    @property
    def spot(self) -> float | None:
        if self.bid is not None and self.ask is not None and self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last


class OpenInterestRecord(BaseModel):
    """Open interest for one contract. Fetched once per session (OI is end-of-day data)."""

    con_id: int
    session_date: date
    open_interest: int = Field(ge=0)
    fetched_at: AwareDatetime
