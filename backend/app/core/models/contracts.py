"""Contract identity models.

`con_id` (IBKR's contract id) is the ONLY identity key in the system.
Symbols, strikes, and rights are descriptive decoration.
"""
from __future__ import annotations

from datetime import date
from enum import Enum, IntEnum

from pydantic import BaseModel, ConfigDict


class OptionRight(str, Enum):
    CALL = "C"
    PUT = "P"


class Tier(IntEnum):
    """Acquisition tier (see PLAN.md §5). Carried for diagnostics/budgeting."""

    T1_STREAM = 1       # continuous near-the-money stream
    T2_FREQUENT = 2     # rotating snapshot pool (30-60s)
    T3_INFREQUENT = 3   # far wings / far expiries (5-15min)


class OptionContract(BaseModel):
    """Reference identity for one option. Frozen value object."""

    model_config = ConfigDict(frozen=True)

    con_id: int
    symbol: str                 # e.g. "SPX"
    trading_class: str          # e.g. "SPX" | "SPXW"
    expiry: date
    strike: float
    right: OptionRight
    multiplier: int = 100
    exchange: str = "SMART"
