"""Smoke test: boot the app with the simulated provider and exercise the REST
endpoints plus the WebSocket bootstrap. No broker, no external infra.

The simulated provider seeds a full option universe and the pipeline computes
one snapshot during startup, so every read below has data without waiting on the
background loop. The recompute interval is pushed high here so that loop stays
out of the way and the test is deterministic (no concurrent SQLite writes).
"""
from __future__ import annotations

import os
import tempfile

# Configure BEFORE importing the app — settings are read at startup.
_TMP_DB = os.path.join(tempfile.gettempdir(), "gex_smoke_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["GEX_PROVIDER"] = "simulated"
os.environ["GEX_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
os.environ["GEX_RECOMPUTE_INTERVAL_S"] = "3600"  # keep the background loop idle
os.environ["GEX_HEARTBEAT_INTERVAL_S"] = "0.5"   # reap the test WS promptly on close

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_smoke():
    with TestClient(app) as client:
        # Liveness
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        # Current snapshot — seeded during startup
        r = client.get("/api/v1/gex/current")
        assert r.status_code == 200, r.text
        snap = r.json()
        assert snap["underlying"] == "SPX"
        assert snap["spot"] > 0
        assert len(snap["profile"]) > 0
        # mockup-shaped sign invariants
        assert snap["call_gex_total"] >= 0
        assert snap["put_gex_total"] <= 0

        # Levels fast path (external service)
        r = client.get("/api/v1/gex/levels")
        assert r.status_code == 200
        assert "regime" in r.json()

        # Flip curve
        r = client.get("/api/v1/gex/flip-curve")
        assert r.status_code == 200
        assert len(r.json()["points"]) > 0

        # Quality
        r = client.get("/api/v1/quality")
        assert r.status_code == 200
        assert r.json()["line_cap"] == 100

        # Meta / reproducibility
        r = client.get("/api/v1/meta/run")
        assert r.status_code == 200
        assert r.json()["provider"] == "simulated"

        # History — the startup seed wrote one row
        r = client.get("/api/v1/gex/history")
        assert r.status_code == 200
        assert len(r.json()) >= 1

        # WebSocket — a bootstrap envelope arrives immediately on connect
        with client.websocket_connect("/api/v1/ws/stream") as ws:
            env = ws.receive_json()
            assert env["v"] == 1
            assert env["msg"]["kind"] in {"gex_snapshot", "quality"}


def teardown_module(module):
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)
