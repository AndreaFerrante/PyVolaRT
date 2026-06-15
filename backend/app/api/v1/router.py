"""Versioned API router.

Everything the service exposes lives under ``/api/v1``: the REST endpoints
(bootstrap, levels, flip curve, history, quality, meta) and the WebSocket feed.
The version prefix plus the envelope ``v`` field are the two halves of the
schema-versioning contract — additive-only within v1.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import rest, ws

router = APIRouter(prefix="/api/v1")
router.include_router(rest.router)
router.include_router(ws.router)
