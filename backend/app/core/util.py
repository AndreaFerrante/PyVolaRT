"""Tiny shared helpers. Kept deliberately minimal."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware 'now' in UTC. Every timestamp in the system uses this."""
    return datetime.now(timezone.utc)
