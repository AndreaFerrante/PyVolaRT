"""Application factory + process lifespan.

Wires the object graph once at startup, runs the pipeline (provider + recompute
loop + heartbeat) for the life of the process, and exposes the FastAPI app.

One process owns one IBKR session and runs a single uvicorn worker:
market-data lines belong to one session, so multiple workers would fight over
the 100-line budget (ARCHITECTURE.md §0). Do not run this with --workers > 1.

Run:
    uvicorn app.main:app --reload                 # simulated provider (default)
    GEX_PROVIDER=ibkr uvicorn app.main:app        # live IB Gateway/TWS (M2-gated)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_router
from app.config import Settings
from app.persistence.db import Database
from app.persistence.repository import Repository
from app.services.gex.engine import GexEngine
from app.services.hub import Hub
from app.services.pipeline import Pipeline
from app.services.providers.base import MarketDataProvider, MarketSink
from app.services.state import MarketState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("gex.main")


def build_provider(settings: Settings, sink: MarketSink) -> MarketDataProvider:
    """Select the data source.

    Defaults to the simulator so the service runs with no broker. ``ibkr`` is the
    M2-gated live path; its import is deferred so ib_async is only required when
    that provider is actually selected.
    """
    if settings.provider == "ibkr":
        from app.services.providers.ibkr import IBKRProvider

        return IBKRProvider(settings, sink)

    from app.services.providers.simulated import SimulatedProvider

    return SimulatedProvider(settings, sink)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()

    # Persistence first: schema must exist before the pipeline writes a snapshot.
    db = Database(settings.database_url)
    await db.create_all()
    repository = Repository(db.sessionmaker)

    # Domain + orchestration object graph.
    state = MarketState(settings.underlying)
    engine = GexEngine()
    hub = Hub()
    provider = build_provider(settings, state)
    pipeline = Pipeline(
        settings=settings,
        provider=provider,
        state=state,
        engine=engine,
        hub=hub,
        repository=repository,
    )

    # Expose what the API layer needs (deps.get_pipeline reads app.state.pipeline).
    app.state.settings = settings
    app.state.pipeline = pipeline
    app.state.db = db

    await pipeline.start()
    log.info(
        "%s ready (provider=%s, underlying=%s, db=%s)",
        settings.app_name,
        settings.provider,
        settings.underlying,
        settings.database_url,
    )
    try:
        yield
    finally:
        await pipeline.stop()
        await db.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="GEX Dashboard API", version="1.0.0", lifespan=lifespan)

    # Settings() is cheap and side-effect-free; read once here for CORS config.
    cors_origins = Settings().cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,  # bearer tokens, not cookies → "*" stays valid
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict:
        """Liveness only — does not assert IBKR connectivity (see /quality)."""
        return {"status": "ok"}

    return app


app = create_app()
