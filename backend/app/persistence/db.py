"""Database engine + session factory.

SQLite (aiosqlite) by default so the service runs with zero infra. Switch to
Postgres with a DSN change only:
    GEX_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/gex
Schema is created on startup for convenience; production should use Alembic.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.persistence.tables import Base


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, future=True)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()
