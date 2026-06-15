"""API dependencies."""
from __future__ import annotations

from fastapi import Request

from app.services.pipeline import Pipeline


def get_pipeline(request: Request) -> Pipeline:
    return request.app.state.pipeline
