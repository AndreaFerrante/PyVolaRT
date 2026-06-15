"""Wire envelope for the WebSocket feed.

A discriminated union keyed on ``kind`` keeps TypeScript codegen clean.
``seq`` is monotonic per run; consumers use it to detect gaps and restarts.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import AwareDatetime, BaseModel, Field

from app.core.models.gex import FlipCurve, GexSnapshot
from app.core.models.quality import DataQuality


class GexSnapshotMsg(BaseModel):
    kind: Literal["gex_snapshot"] = "gex_snapshot"
    data: GexSnapshot


class FlipCurveMsg(BaseModel):
    kind: Literal["flip_curve"] = "flip_curve"
    data: FlipCurve


class QualityMsg(BaseModel):
    kind: Literal["quality"] = "quality"
    data: DataQuality


class HeartbeatMsg(BaseModel):
    kind: Literal["heartbeat"] = "heartbeat"
    data: AwareDatetime  # lets consumers distinguish "quiet" from "dead"


WsMessage = Annotated[
    Union[GexSnapshotMsg, FlipCurveMsg, QualityMsg, HeartbeatMsg],
    Field(discriminator="kind"),
]


class WsEnvelope(BaseModel):
    v: Literal[1] = 1          # schema version; additive-only within v1
    seq: int
    sent_at: AwareDatetime
    msg: WsMessage
