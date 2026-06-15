"""Persistence tables.

The full ``GexSnapshot`` is stored as JSON (``payload``) for faithful
reconstruction, with a few scalar columns promoted for indexing/filtering and
cheap aggregate queries. ``ts_epoch`` is used for range queries to sidestep
SQLite timezone-comparison quirks.
"""
from __future__ import annotations

from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GexSnapshotRow(Base):
    __tablename__ = "gex_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    ts_epoch: Mapped[float] = mapped_column(Float, index=True)
    underlying: Mapped[str] = mapped_column(String(16), index=True)
    net_gex: Mapped[float] = mapped_column(Float)
    regime: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON)
