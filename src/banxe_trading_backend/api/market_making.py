"""Market-making advisory preview router (S12 / X9.1) — INTERNAL, mock/sandbox.

POST /api/v1/mm/preview maps a market-making strategy request onto an ADVISORY
quote ladder around a mid price (mock strategy by default). It composes over the
existing ExchangePort for the mid (mock rate) without changing its semantics.

STRICTLY advisory / pre-production:
  * the rungs are UNSIGNED suggestions — nothing is signed, submitted, or executed
    (signed:false, submitted:false; self-custodial);
  * mock/sandbox only, no live venue, no keys, no network in the path;
  * INTERNAL terminal endpoint — NOT on the external /v1 BaaS facade.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request

from banxe_trading_backend.models import split_symbol
from banxe_trading_backend.ports import (
    ExchangePort,
    MarketMakingPort,
    MmPreviewRequest,
    MmPreviewResponse,
)

from .deps import get_exchange

router = APIRouter(prefix="/mm", tags=["market-making"])

_MAX_LEVELS = 10
_QUOTES = ("USDT", "USDC", "USD", "DAI", "EUR", "BTC", "ETH")
_DISCLAIMER = (
    "Sandbox/pre-production market-making PREVIEW — advisory UNSIGNED quote ladder. "
    "Nothing is signed, submitted, or executed; the backend holds no keys and no "
    "live venue is contacted. Mock data, no live chain. Self-custodial; NOT orders."
)


def _split_asset(asset: str) -> tuple[str, str]:
    if "-" in asset or "/" in asset:
        return split_symbol(asset)
    upper = asset.upper()
    for quote in sorted(_QUOTES, key=len, reverse=True):
        if upper.endswith(quote) and len(upper) > len(quote):
            return upper[: -len(quote)], quote
    raise HTTPException(status_code=422, detail=f"cannot split asset {asset!r}")


@router.post("/preview", response_model=MmPreviewResponse)
async def mm_preview(
    body: MmPreviewRequest,
    request: Request,
    exchange: ExchangePort = Depends(get_exchange),
) -> MmPreviewResponse:
    if body.spread_bps <= 0:
        raise HTTPException(status_code=422, detail="spreadBps must be > 0")
    if not 1 <= body.levels <= _MAX_LEVELS:
        raise HTTPException(status_code=422, detail=f"levels must be 1..{_MAX_LEVELS}")
    try:
        size = Decimal(body.size_usd)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail="invalid sizeUsd") from exc
    if size <= 0:
        raise HTTPException(status_code=422, detail="sizeUsd must be > 0")

    # Mid from the request, else the (mock) rate — composes over ExchangePort.
    if body.mid_price is not None:
        try:
            mid = Decimal(body.mid_price)
        except InvalidOperation as exc:
            raise HTTPException(status_code=422, detail="invalid midPrice") from exc
    else:
        base, quote = _split_asset(body.asset)
        rate = await exchange.get_rate(base, quote)
        mid = (Decimal(rate.bid) + Decimal(rate.ask)) / 2
    if mid <= 0:
        raise HTTPException(status_code=422, detail="mid must be > 0")

    strategy: MarketMakingPort = request.app.state.mm
    rungs = strategy.build_ladder(
        asset=body.asset,
        mid=mid,
        spread_bps=body.spread_bps,
        levels=body.levels,
        size_usd=size,
    )
    return MmPreviewResponse(
        asset=body.asset,
        mid=str(mid.quantize(Decimal("0.01"))),
        mode="sandbox-mock",
        signed=False,
        submitted=False,
        rungs=rungs,
        source="sandbox-mock",
        disclaimer=_DISCLAIMER,
    )
