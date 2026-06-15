"""In-process broadcast hub.

The single fan-out point: the recompute loop publishes messages; every connected
WebSocket holds a bounded queue here. Backpressure is drop-oldest, so a slow
client loses intermediate snapshots rather than blocking the producer or growing
memory without bound. Latest snapshot/quality envelopes are cached so a freshly
connected client can be bootstrapped immediately.
"""
from __future__ import annotations

import asyncio

from app.core.models.envelope import WsEnvelope, WsMessage
from app.core.util import utcnow


class Hub:
    def __init__(self, queue_maxsize: int = 32) -> None:
        self._subscribers: set[asyncio.Queue[WsEnvelope]] = set()
        self._maxsize = queue_maxsize
        self._seq = 0
        self._latest_snapshot: WsEnvelope | None = None
        self._latest_quality: WsEnvelope | None = None
        self._latest_flip: WsEnvelope | None = None

    def subscribe(self) -> asyncio.Queue[WsEnvelope]:
        q: asyncio.Queue[WsEnvelope] = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[WsEnvelope]) -> None:
        self._subscribers.discard(q)

    def publish(self, msg: WsMessage) -> WsEnvelope:
        self._seq += 1
        env = WsEnvelope(seq=self._seq, sent_at=utcnow(), msg=msg)

        if msg.kind == "gex_snapshot":
            self._latest_snapshot = env
        elif msg.kind == "quality":
            self._latest_quality = env
        elif msg.kind == "flip_curve":
            self._latest_flip = env

        for q in self._subscribers:
            if q.full():
                try:
                    q.get_nowait()  # drop oldest
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(env)
            except asyncio.QueueFull:
                pass
        return env

    def bootstrap(self) -> list[WsEnvelope]:
        """Envelopes a new subscriber should receive on connect."""
        return [e for e in (self._latest_snapshot, self._latest_quality) if e is not None]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
