"""Execution intent-preview router (T9.1) — INTERNAL, mock/sandbox-only.

POST /api/v1/execution/intent-preview maps a DSE advisory action onto an UNSIGNED
execution intent (via the configured ExchangePort; mock by default). This is the
internal "advice → unsigned intent" bridge — execution PREPARATION only:
  * NOTHING is signed or submitted (self-custodial; the client wallet signs);
  * mock/sandbox by default — no live chain, no keys, no real execution;
  * advisory / pre-production — NO SLA, NO billing, NO partner obligations.

This is an internal terminal endpoint, NOT part of the external partner BaaS
surface (it is not exposed via the /v1/... facade).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from banxe_trading_backend.ports import ExchangePort
from banxe_trading_backend.services.intent_preview import (
    IntentPreviewRequest,
    IntentPreviewResponse,
    IntentPreviewService,
)

from .deps import get_exchange

router = APIRouter(prefix="/execution", tags=["execution"])


@router.post("/intent-preview", response_model=IntentPreviewResponse)
async def intent_preview(
    body: IntentPreviewRequest,
    request: Request,  # noqa: ARG001 - kept for symmetry / future gating
    exchange: ExchangePort = Depends(get_exchange),
) -> IntentPreviewResponse:
    service = IntentPreviewService(exchange)
    try:
        return await service.preview(body)
    except ValueError as exc:
        # invalid asset / non-positive notional / submit safety-rail
        raise HTTPException(status_code=422, detail=str(exc)) from exc
