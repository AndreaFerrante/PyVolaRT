"""Single configuration source. Env-overridable with the ``GEX_`` prefix.

A hash of the resolved config is recorded per run for reproducibility.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GEX_", env_file=".env", extra="ignore")

    app_name: str = "GEX Dashboard API"

    # --- provider selection ---
    # "simulated": runs with no broker (default, dev/frontend).
    # "ibkr": connects to a live IB Gateway/TWS (requires M2 validation).
    provider: Literal["simulated", "ibkr"] = "simulated"

    # --- persistence ---
    # SQLite by default so the service runs out of the box. For production use
    # Postgres: GEX_DATABASE_URL=postgresql+asyncpg://user:pass@host/db
    database_url: str = "sqlite+aiosqlite:///./gex.db"
    history_default_hours: int = 6
    history_retention_days: float = 7.0   # older snapshots are pruned hourly

    # --- CORS ---
    # The React dev server runs on a different origin. "*" is fine for a local
    # tool; lock this down in production, e.g.
    # GEX_CORS_ORIGINS='["https://dashboard.internal"]'
    cors_origins: list[str] = ["*"]

    # --- universe / windowing ---
    underlying: str = "SPX"
    strike_spacing: float = 5.0
    ntm_strikes_each_side: int = 30

    # --- line budget (PLAN D8) ---
    line_cap: int = 100
    line_reserve: int = 5

    # --- compute cadence ---
    recompute_interval_s: float = 2.0
    heartbeat_interval_s: float = 10.0
    risk_free_rate: float = 0.04

    # --- flip-curve sweep ---
    flip_grid_points: int = 81
    flip_grid_span: float = 0.10   # +/- 10% around spot

    # --- quality thresholds ---
    spot_sla_s: float = 10.0
    degraded_coverage_threshold: float = 0.80

    # --- simulated provider ---
    sim_initial_spot: float = 6000.0
    sim_base_iv: float = 0.18
    sim_tick_interval_s: float = 1.0
    sim_expiry_days: int = 7

    # --- IBKR provider ---
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 4001
    ibkr_client_id: int = 11

    def config_hash(self) -> str:
        blob = json.dumps(self.model_dump(), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]
