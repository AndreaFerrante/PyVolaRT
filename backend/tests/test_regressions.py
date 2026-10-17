"""Regression tests for history ordering, retention, and stale-feed detection."""
from __future__ import annotations

import asyncio
from datetime import timedelta

from app.config import Settings
from app.core.models.gex import GexLevels, GexSnapshot, Regime
from app.core.models.quality import DataQuality, FeedStatus
from app.core.util import utcnow
from app.persistence.db import Database
from app.persistence.repository import Repository
from app.services.gex.engine import GexEngine
from app.services.hub import Hub
from app.services.pipeline import Pipeline
from app.services.providers.simulated import SimulatedProvider
from app.services.state import MarketState


def _snapshot(ts) -> GexSnapshot:
    return GexSnapshot(
        ts=ts, underlying="SPX", spot=6000.0,
        net_gex=0.0, gross_gex=0.0, call_gex_total=0.0, put_gex_total=0.0,
        call_oi_total=0, put_oi_total=0, total_oi=0,
        regime=Regime.UNKNOWN, levels=GexLevels(), profile=[], expiries_included=[],
        quality=DataQuality(status=FeedStatus.LIVE, t1_coverage=1.0),
    )


def test_history_returns_newest_rows_and_prune_deletes_old(tmp_path):
    async def run():
        db = Database(f"sqlite+aiosqlite:///{tmp_path / 'h.db'}")
        await db.create_all()
        repo = Repository(db.sessionmaker)
        t0 = utcnow() - timedelta(minutes=10)
        times = [t0 + timedelta(seconds=i) for i in range(10)]
        for t in times:
            await repo.save_snapshot(_snapshot(t), run_id="r")

        window = (t0 - timedelta(seconds=1), t0 + timedelta(minutes=1))
        latest3 = await repo.get_history("SPX", *window, limit=3, step=1)
        assert [s.ts for s in latest3] == times[-3:]
        strided = await repo.get_history("SPX", *window, limit=3, step=2)
        assert [s.ts for s in strided] == [times[5], times[7], times[9]]

        assert await repo.prune(times[4]) == 4
        assert len(await repo.get_history("SPX", *window, limit=100, step=1)) == 6
        await db.dispose()

    asyncio.run(run())


def test_silent_feed_goes_stale(tmp_path):
    async def run():
        settings = Settings(
            database_url=f"sqlite+aiosqlite:///{tmp_path / 's.db'}",
            recompute_interval_s=0.05,
            spot_sla_s=0.2,
            sim_tick_interval_s=3600,  # seeds once on start, then never ticks
        )
        db = Database(settings.database_url)
        await db.create_all()
        state = MarketState(settings.underlying)
        pipeline = Pipeline(
            settings=settings, provider=SimulatedProvider(settings, state), state=state,
            engine=GexEngine(), hub=Hub(), repository=Repository(db.sessionmaker),
        )
        await pipeline.start()
        try:
            assert pipeline.latest_quality.status is FeedStatus.LIVE
            await asyncio.sleep(0.5)
            assert pipeline.latest_quality.status is FeedStatus.STALE
            # served snapshot (/gex/current, /gex/levels) must not keep claiming LIVE
            assert pipeline.latest_snapshot.quality.status is FeedStatus.STALE
        finally:
            await pipeline.stop()
            await db.dispose()

    asyncio.run(run())
