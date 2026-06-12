"""Orders REST router (ADR-021 §D3) — maps the FE body onto ExchangePort.

place/cancel/status only. positions/balances are a GAP (no ExchangePort op) —
they need an account/portfolio source and are out of scope for the skeleton.
TODO(ADR-021 governance): decide the positions/balances data source.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from banxe_trading_backend.models import (
    CancelResult,
    ExchangeOrderRequest,
    OrderResult,
    PlaceOrderRequest,
    split_symbol,
)
from banxe_trading_backend.ports import ExchangePort

from .deps import get_exchange

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResult)
async def place_order(
    body: PlaceOrderRequest,
    exchange: ExchangePort = Depends(get_exchange),
) -> OrderResult:
    base, quote = split_symbol(body.symbol)
    order = ExchangeOrderRequest(
        base_asset=base,
        quote_asset=quote,
        side=body.side,
        type=body.type,
        amount=body.amount,
        client_order_id=body.client_order_id,
        correlation_id=body.correlation_id,
        limit_price=body.limit_price,
    )
    return await exchange.place_order(order)


@router.delete("/{order_id}", response_model=CancelResult)
async def cancel_order(
    order_id: str,
    exchange: ExchangePort = Depends(get_exchange),
) -> CancelResult:
    cancelled = await exchange.cancel_order(order_id)
    return CancelResult(order_id=order_id, cancelled=cancelled)


@router.get("/{order_id}", response_model=OrderResult)
async def get_order_status(
    order_id: str,
    exchange: ExchangePort = Depends(get_exchange),
) -> OrderResult:
    return await exchange.get_order_status(order_id)
