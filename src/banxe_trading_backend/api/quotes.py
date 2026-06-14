"""Quotes REST router (ADR-083 QuotePort; S6.5).

GET /quote → a normalized aggregator quote via the configured QuotePort
(mock by default; LI.FI when ``BANXE_QUOTE_PROVIDER=lifi``). Read-only estimate;
self-custodial (any resulting swap is signed by the client wallet).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from banxe_trading_backend.models import QuoteRequest, QuoteResponse
from banxe_trading_backend.ports import ExchangeError, QuotePort

from .deps import get_quote_provider

router = APIRouter(prefix="/quote", tags=["quote"])


@router.get("", response_model=QuoteResponse)
async def get_quote(
    from_chain: str = Query(..., alias="fromChain", min_length=1),
    to_chain: str = Query(..., alias="toChain", min_length=1),
    from_token: str = Query(..., alias="fromToken", min_length=1),
    to_token: str = Query(..., alias="toToken", min_length=1),
    amount: str = Query(..., min_length=1),
    from_address: str | None = Query(None, alias="fromAddress"),
    slippage: str | None = Query(None),
    provider: QuotePort = Depends(get_quote_provider),
) -> QuoteResponse:
    request = QuoteRequest(
        from_chain=from_chain,
        to_chain=to_chain,
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        from_address=from_address,
        slippage=slippage,
    )
    try:
        return await provider.get_quote(request)
    except ExchangeError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
