"""Rate REST router (ADR-021 §D3) — read-only spot quote via ExchangePort."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from banxe_trading_backend.models import RateQuote
from banxe_trading_backend.ports import ExchangePort

from .deps import get_exchange

router = APIRouter(prefix="/rate", tags=["rate"])


@router.get("", response_model=RateQuote)
async def get_rate(
    base: str = Query(..., min_length=1),
    quote: str = Query(..., min_length=1),
    exchange: ExchangePort = Depends(get_exchange),
) -> RateQuote:
    # Honour ttlSeconds at the consumer; a stale quote must be refused (StaleRate).
    return await exchange.get_rate(base, quote)
