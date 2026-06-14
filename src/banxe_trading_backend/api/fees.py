"""Dynamic fee preview router (S13 / X9.2) — INTERNAL, advisory/analytics-only.

POST /api/v1/fees/preview returns a fee ATTRIBUTION decomposition (metadata) for a
candidate action. STRICTLY advisory:
  * NO real charges, invoices, payments, or billing — metadata only;
  * NO billing integrations, NO on-chain settlement, NO keys, NO network;
  * unsigned / not-submitted (signed:false, submitted:false);
  * INTERNAL terminal endpoint — NOT on the external /v1 BaaS facade.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, Request

from banxe_trading_backend.ports import (
    FeeEnginePort,
    FeePreviewRequest,
    FeePreviewResponse,
)
from banxe_trading_backend.services.decision_lineage import record_lineage

router = APIRouter(prefix="/fees", tags=["fees"])

_DISCLAIMER = (
    "Sandbox-only dynamic fee PREVIEW — advisory attribution/analytics metadata. "
    "No real billing, invoicing, payment, or on-chain settlement; nothing is "
    "charged, signed, or submitted. Mock fixtures, deterministic, no network."
)


@router.post("/preview", response_model=FeePreviewResponse)
async def fees_preview(body: FeePreviewRequest, request: Request) -> FeePreviewResponse:
    if not body.asset.strip():
        raise HTTPException(status_code=422, detail="asset must be non-empty")
    try:
        notional = Decimal(body.notional_usd)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail="invalid notionalUsd") from exc
    if notional <= 0:
        raise HTTPException(status_code=422, detail="notionalUsd must be > 0")

    engine: FeeEnginePort = request.app.state.fee_engine
    components = engine.compute(body)
    total_bps = sum((Decimal(c.bps) for c in components), Decimal(0))
    total_usd = sum((Decimal(c.usd) for c in components), Decimal(0))
    response = FeePreviewResponse(
        mode="sandbox-mock",
        signed=False,
        submitted=False,
        asset=body.asset,
        notional_usd=body.notional_usd,
        total_fee_bps=str(total_bps.quantize(Decimal("0.01"))),
        total_fee_usd=str(total_usd.quantize(Decimal("0.0001"))),
        components=components,
        disclaimer=_DISCLAIMER,
    )
    # G1L: inert audit capture (fail-closed; never changes the response).
    record_lineage(request, layer="FEE_PREVIEW", body=body, response=response)
    return response
