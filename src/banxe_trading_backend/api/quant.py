"""Quant-moat advisory preview router (S14 / X9.3) — INTERNAL, mock-safe.

POST /api/v1/quant/preview returns OPTIONAL quant analytics (fair-value gap,
stress scenario, volatility regime, flags) as ADVISORY metadata. STRICTLY
mock-safe: no live quant models, no live price feeds, no keys, no network, no
trading decisions. INTERNAL terminal endpoint — NOT on the external /v1 facade.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, Request

from banxe_trading_backend.ports import (
    QuantEnginePort,
    QuantPreviewRequest,
    QuantPreviewResponse,
)
from banxe_trading_backend.services.decision_lineage import record_lineage

router = APIRouter(prefix="/quant", tags=["quant"])


@router.post("/preview", response_model=QuantPreviewResponse)
async def quant_preview(body: QuantPreviewRequest, request: Request) -> QuantPreviewResponse:
    if not body.asset.strip():
        raise HTTPException(status_code=422, detail="asset must be non-empty")
    if body.horizon_days <= 0:
        raise HTTPException(status_code=422, detail="horizonDays must be > 0")
    try:
        notional = Decimal(body.notional_usd)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail="invalid notionalUsd") from exc
    if notional <= 0:
        raise HTTPException(status_code=422, detail="notionalUsd must be > 0")

    engine: QuantEnginePort = request.app.state.quant
    response = engine.compute(body)
    # G1L: inert audit capture (fail-closed; never changes the response).
    record_lineage(request, layer="QUANT_PREVIEW", body=body, response=response)
    return response
