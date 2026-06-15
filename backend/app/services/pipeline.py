"""Pipeline — the orchestration layer.

Owns the provider, the recompute loop, and the heartbeat. On each cycle it takes
a consistent read of market state, derives feed quality, runs the flip-curve and
GEX engine, then fans the result out to the hub (WebSocket consumers) and the
repository (history). The provider only writes into state and flips a dirty bit;
this loop decides *when* to recompute (throttled — PLAN.md D5).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import uuid4

from app.config import Settings
from app.core.models.envelope import (
    FlipCurveMsg,
    GexSnapshotMsg,
    HeartbeatMsg,
    QualityMsg,
)
from app.core.models.gex import FlipCurve, GexSnapshot
from app.core.models.quality import DataQuality, FeedStatus
from app.core.util import utcnow
from app.services.gex.engine import EngineInputs, GexEngine
from app.services.gex.flip import compute_flip_curve
from app.services.hub import Hub
from app.services.providers.base import MarketDataProvider
from app.services.state import MarketState
from app.persistence.repository import Repository

log = logging.getLogger("gex.pipeline")


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        provider: MarketDataProvider,
        state: MarketState,
        engine: GexEngine,
        hub: Hub,
        repository: Repository,
    ) -> None:
        self.config = settings
        self.provider = provider
        self.state = state
        self.engine = engine
        self.hub = hub
        self.repository = repository

        self.run_id = uuid4().hex[:12]
        self.started_at = utcnow()
        self.latest_snapshot: GexSnapshot | None = None
        self.latest_flip: FlipCurve | None = None
        self.latest_quality: DataQuality | None = None

        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._last_status: FeedStatus | None = None

    async def start(self) -> None:
        await self.provider.start()
        await self._recompute_once()  # seed REST/WS bootstrap immediately
        self._running = True
        self._tasks = [
            asyncio.create_task(self._recompute_loop()),
            asyncio.create_task(self._heartbeat_loop()),
        ]
        log.info("pipeline started run_id=%s provider=%s", self.run_id, self.config.provider)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.provider.stop()
        log.info("pipeline stopped run_id=%s", self.run_id)

    # --- loops -------------------------------------------------------------
    async def _recompute_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.config.recompute_interval_s)
            if self.state.consume_dirty():
                try:
                    await self._recompute_once()
                except Exception:  # never let one bad cycle kill the loop
                    log.exception("recompute cycle failed")

    async def _heartbeat_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.config.heartbeat_interval_s)
            self.hub.publish(HeartbeatMsg(data=utcnow()))

    # --- one cycle ---------------------------------------------------------
    async def _recompute_once(self) -> None:
        now = utcnow()
        inputs = self.state.snapshot_inputs(now, self.config.risk_free_rate)
        quality = self._build_quality(now, inputs)

        # Always surface quality changes, even when we cannot compute GEX yet.
        self.latest_quality = quality
        self._publish_quality_if_changed(quality)

        if inputs.spot is None or inputs.spot <= 0 or not inputs.contracts:
            return

        flip = compute_flip_curve(inputs, self.config.flip_grid_points, self.config.flip_grid_span)
        snapshot = self.engine.compute(inputs, quality=quality, zero_gamma=flip.zero_crossing)

        self.latest_flip = flip
        self.latest_snapshot = snapshot

        self.hub.publish(GexSnapshotMsg(data=snapshot))
        self.hub.publish(FlipCurveMsg(data=flip))
        await self.repository.save_snapshot(snapshot, run_id=self.run_id)

    # --- quality -----------------------------------------------------------
    def _build_quality(self, now: datetime, inputs: EngineInputs) -> DataQuality:
        health = self.provider.health()
        spot_age = self.state.spot_age_s(now)
        total = self.state.contract_count()
        coverage = (self.state.fresh_greeks_count() / total) if total else 0.0
        status = self._derive_status(health.connected, spot_age, coverage)
        return DataQuality(
            status=status,
            t1_coverage=coverage,
            spot_age_s=spot_age,
            oi_session_date=self.state.oi_session_date(),
            lines_in_use=health.lines_in_use,
            line_cap=self.config.line_cap,
        )

    def _derive_status(self, connected: bool, spot_age: float | None, coverage: float) -> FeedStatus:
        # NOTE: market-hours gating (OFFLINE_HOURS) is the scheduler's job (M6);
        # the simulated provider is treated as always-on.
        if not connected:
            return FeedStatus.DISCONNECTED
        if spot_age is None or spot_age > self.config.spot_sla_s:
            return FeedStatus.STALE
        if coverage < self.config.degraded_coverage_threshold:
            return FeedStatus.DEGRADED
        return FeedStatus.LIVE

    def _publish_quality_if_changed(self, quality: DataQuality) -> None:
        if quality.status != self._last_status:
            self._last_status = quality.status
            self.hub.publish(QualityMsg(data=quality))
