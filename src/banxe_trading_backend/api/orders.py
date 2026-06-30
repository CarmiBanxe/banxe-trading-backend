"""Orders REST router (ADR-021 §D3) — maps the FE body onto ExchangePort.

Self-custodial (ADR-083): for the dYdX provider, ``place_order`` returns an
**unsigned order intent** (in OrderResult.raw) for the client wallet to sign —
the backend never signs or submits. Order endpoints require the SIWE wallet
session when ``auth_enabled``; the §D3 7-class error model maps to HTTP.

RED-zone S6.4-EN controls on the order-placement surface (all routes):
* **Ruflo** (regulatory; BUG-005) — every order routes through the regulatory
  check (mock allow this sprint; live Ruflo provider is OPERATOR-GATED).
* **HITL** (BUG-007) — under the live ``dydx`` exchange route, placement
  requires an explicit operator confirmation header; missing = HTTP 428.

positions/balances remain a GAP (no ExchangePort op) — out of scope here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from banxe_trading_backend.models import (
    CancelResult,
    ExchangeOrderRequest,
    OrderResult,
    PlaceOrderRequest,
    split_symbol,
)
from banxe_trading_backend.ports import ExchangeError, ExchangePort
from banxe_trading_backend.ports.wallet_auth_port import Session
from banxe_trading_backend.services.order_controls import (
    HITL_HEADER,
    assert_hitl_confirmed,
    assert_ruflo_allowed,
)

from .deps import get_exchange, require_session

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResult)
async def place_order(
    request: Request,
    body: PlaceOrderRequest,
    session: Session | None = Depends(require_session),
    exchange: ExchangePort = Depends(get_exchange),
) -> OrderResult:
    # RED-zone S6.4-EN controls — Ruflo regulatory check on every order surface
    # (BUG-005), then HITL gate on the live exchange route (BUG-007).
    assert_ruflo_allowed(
        client_order_id=body.client_order_id,
        owner_address=session.address if session is not None else None,
    )
    if request.app.state.exchange_route == "dydx":
        assert_hitl_confirmed(header_value=request.headers.get(HITL_HEADER))

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
        time_in_force=body.time_in_force,
        reduce_only=body.reduce_only,
        # Self-custodial: the order owner is the authenticated wallet address.
        owner_address=session.address if session is not None else None,
    )
    try:
        return await exchange.place_order(order)
    except ExchangeError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.delete("/{order_id}", response_model=CancelResult)
async def cancel_order(
    order_id: str,
    session: Session | None = Depends(require_session),
    exchange: ExchangePort = Depends(get_exchange),
) -> CancelResult:
    try:
        cancelled = await exchange.cancel_order(order_id)
    except ExchangeError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    return CancelResult(order_id=order_id, cancelled=cancelled)


@router.get("/{order_id}", response_model=OrderResult)
async def get_order_status(
    order_id: str,
    session: Session | None = Depends(require_session),
    exchange: ExchangePort = Depends(get_exchange),
) -> OrderResult:
    try:
        return await exchange.get_order_status(order_id)
    except ExchangeError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
