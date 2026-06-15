"""Data-quality models. Make degradation measurable instead of silent."""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel


class FeedStatus(str, Enum):
    LIVE = "live"                  # spot fresh, Tier-1 coverage above threshold
    DEGRADED = "degraded"          # partial coverage / fallbacks active
    STALE = "stale"                # spot or Tier-1 older than SLA
    OFFLINE_HOURS = "offline_hours"  # scheduler-gated (market closed)
    DISCONNECTED = "disconnected"  # IBKR session down


class DataQuality(BaseModel):
    status: FeedStatus
    t1_coverage: float             # fraction of contracts with fresh usable greeks (0-1)
    spot_age_s: float | None = None
    oi_session_date: date | None = None
    lines_in_use: int = 0
    line_cap: int = 100            # assertion surface for the line budget (PLAN D8)
