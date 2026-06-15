"""Repository — the only place that talks to the snapshot table.

Stores domain models, returns domain models. Callers never see ORM rows.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.models.gex import GexSnapshot
from app.persistence.tables import GexSnapshotRow


class Repository:
    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def save_snapshot(self, snapshot: GexSnapshot, run_id: str) -> None:
        async with self._sessionmaker() as session:
            session.add(
                GexSnapshotRow(
                    run_id=run_id,
                    ts_epoch=snapshot.ts.timestamp(),
                    underlying=snapshot.underlying,
                    net_gex=snapshot.net_gex,
                    regime=snapshot.regime.value,
                    payload=snapshot.model_dump(mode="json"),
                )
            )
            await session.commit()

    async def get_history(
        self,
        underlying: str,
        start: datetime,
        end: datetime,
        limit: int,
        step: int,
    ) -> list[GexSnapshot]:
        stmt = (
            select(GexSnapshotRow)
            .where(
                GexSnapshotRow.underlying == underlying,
                GexSnapshotRow.ts_epoch >= start.timestamp(),
                GexSnapshotRow.ts_epoch <= end.timestamp(),
            )
            .order_by(GexSnapshotRow.ts_epoch.asc())
        )
        async with self._sessionmaker() as session:
            rows = (await session.execute(stmt)).scalars().all()

        if step > 1:
            rows = rows[::step]
        rows = rows[:limit]
        return [GexSnapshot.model_validate(row.payload) for row in rows]
