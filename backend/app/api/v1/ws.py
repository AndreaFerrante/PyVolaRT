"""WebSocket endpoint — the canonical real-time feed.

A client connects, immediately receives a bootstrap (the latest snapshot and the
latest quality status), then receives every envelope the hub publishes: GEX
snapshots, flip curves, quality changes, and heartbeats.

Backpressure lives in the hub (a drop-oldest, bounded queue per connection), so
this endpoint stays deliberately thin: subscribe, forward each envelope as JSON
text, unsubscribe on the way out. A disconnected client is reaped on the next
publish to its queue — in practice within one heartbeat interval (~10 s), since
heartbeats keep the loop ticking even when the market is quiet. That latency is
fine here: this is a low-fanout internal feed (one dashboard, one external
consumer), not a high-concurrency public socket.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.pipeline import Pipeline

log = logging.getLogger("gex.ws")

router = APIRouter()


@router.websocket("/ws/stream")
async def stream(websocket: WebSocket) -> None:
    # WebSocket routes can't use the Request-based dependency, so read the
    # pipeline off app state directly (same object get_pipeline returns).
    pipeline: Pipeline = websocket.app.state.pipeline
    hub = pipeline.hub

    await websocket.accept()
    queue = hub.subscribe()
    log.info("ws client connected (total=%d)", hub.subscriber_count)

    try:
        # Bootstrap: make a freshly-connected client useful before the next tick.
        for env in hub.bootstrap():
            await websocket.send_text(env.model_dump_json())

        # Forward every published envelope until the client goes away (the next
        # send after a client close raises WebSocketDisconnect).
        while True:
            env = await queue.get()
            await websocket.send_text(env.model_dump_json())
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - defensive: log unexpected send failures
        log.exception("ws send loop failed")
    finally:
        hub.unsubscribe(queue)
        log.info("ws client disconnected (total=%d)", hub.subscriber_count)
