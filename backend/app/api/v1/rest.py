"""REST routes.

Push (WebSocket) is the canonical feed; these endpoints serve bootstrap,
history, and poll-style consumers. ``/gex/current`` and ``/gex/levels`` read the
last computed snapshot from memory; ``/gex/history`` reads Postgres/SQLite.
Every payload is one of the shared Pydantic models.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_pipeline
from app.core.models.gex import FlipCurve, GexSnapshot, LevelsResponse
from app.core.models.quality import DataQuality
from app.core.util import utcnow
from app.services.pipeline import Pipeline

router = APIRouter(tags=["gex"])


def _require_snapshot(pipeline: Pipeline) -> GexSnapshot:
    if pipeline.latest_snapshot is None:
        raise HTTPException(status_code=503, detail="no snapshot computed yet")
    return pipeline.latest_snapshot


@router.get("/gex/current", response_model=GexSnapshot)
def get_current(pipeline: Pipeline = Depends(get_pipeline)) -> GexSnapshot:
    return _require_snapshot(pipeline)


@router.get("/gex/levels", response_model=LevelsResponse)
def get_levels(pipeline: Pipeline = Depends(get_pipeline)) -> LevelsResponse:
    s = _require_snapshot(pipeline)
    return LevelsResponse(
        ts=s.ts,
        underlying=s.underlying,
        spot=s.spot,
        regime=s.regime,
        levels=s.levels,
        quality=s.quality,
    )


@router.get("/gex/flip-curve", response_model=FlipCurve)
def get_flip_curve(pipeline: Pipeline = Depends(get_pipeline)) -> FlipCurve:
    if pipeline.latest_flip is None:
        raise HTTPException(status_code=503, detail="no flip curve computed yet")
    return pipeline.latest_flip


@router.get("/quality", response_model=DataQuality)
def get_quality(pipeline: Pipeline = Depends(get_pipeline)) -> DataQuality:
    if pipeline.latest_quality is None:
        raise HTTPException(status_code=503, detail="no quality computed yet")
    return pipeline.latest_quality


@router.get("/gex/history", response_model=list[GexSnapshot])
async def get_history(
    pipeline: Pipeline = Depends(get_pipeline),
    start: datetime | None = Query(default=None, description="ISO-8601; default end - history window"),
    end: datetime | None = Query(default=None, description="ISO-8601; default now"),
    underlying: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    step: int = Query(default=1, ge=1, description="stride downsample, e.g. 5 = every 5th snapshot"),
) -> list[GexSnapshot]:
    sym = underlying or pipeline.config.underlying
    end = end or utcnow()
    start = start or (end - timedelta(hours=pipeline.config.history_default_hours))
    return await pipeline.repository.get_history(sym, start, end, limit, step)


@router.get("/meta/run")
def get_meta(pipeline: Pipeline = Depends(get_pipeline)) -> dict:
    return {
        "run_id": pipeline.run_id,
        "started_at": pipeline.started_at.isoformat(),
        "provider": pipeline.config.provider,
        "underlying": pipeline.config.underlying,
        "line_cap": pipeline.config.line_cap,
        "config_hash": pipeline.config.config_hash(),
    }
