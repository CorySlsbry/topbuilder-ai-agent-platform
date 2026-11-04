"""Liveness / readiness probes."""
from __future__ import annotations

from fastapi import APIRouter

from app.db import healthcheck

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db() -> dict:
    try:
        ok = await healthcheck()
        return {"status": "ok" if ok else "degraded"}
    except Exception as exc:  # surfaced for readiness checks, not raised
        return {"status": "down", "error": str(exc)}
