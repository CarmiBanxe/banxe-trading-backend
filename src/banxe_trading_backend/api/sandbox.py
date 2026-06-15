"""Unified sandbox-status router (SBOX-1) — INTERNAL, mock-safe, read-only.

GET /api/v1/sandbox/status returns one descriptive snapshot of the sandbox posture
(advisory-only, unsigned, no live providers / billing / KYB) over the delivered
advisory seams. It is a terminal/internal endpoint — NOT part of the external `/v1`
BaaS facade — and activates nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from banxe_trading_backend.services.sandbox_profile import (
    SandboxStatusResponse,
    sandbox_status_response,
)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


@router.get("/status", response_model=SandboxStatusResponse)
async def sandbox_status(request: Request) -> SandboxStatusResponse:
    return sandbox_status_response(request.app.state.settings)
