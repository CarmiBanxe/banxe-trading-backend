"""ExchangePort — network-side Protocol mirroring the payment-core contract.

This is the seam the trading-backend consumes for orders/rate. The REAL adapter
(governance-gated) binds to ``banxe-payment-core``'s in-process ExchangePort —
it is NOT re-implemented here (ADR-021 D1: reuse, do not duplicate). The
skeleton ships only ``InMemoryMockExchange`` so the REST surface is testable
without payment-core or a live exchange.

Idempotency (contract): ``place_order`` MUST be idempotent on ``client_order_id``
— a replay returns the original OrderResult and never double-executes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from banxe_trading_backend.models import (
    ExchangeOrderRequest,
    OrderResult,
    OrderState,
    RateQuote,
)


@runtime_checkable
class ExchangePort(Protocol):
    """Orders + rate. Mirrors payment-core's ExchangePort (async transport seam)."""

    async def get_rate(self, base: str, quote: str) -> RateQuote: ...

    async def place_order(self, order: ExchangeOrderRequest) -> OrderResult: ...

    async def cancel_order(self, order_id: str) -> bool: ...

    async def get_order_status(self, order_id: str) -> OrderResult: ...


class InMemoryMockExchange:
    """Deterministic mock ExchangePort — NO live exchange.

    TODO(ADR-021 governance): replace with the real payment-core-bound adapter
    (EXCHANGE_PROVIDER selection). This mock exists only for the skeleton/tests.
    """

    def __init__(self) -> None:
        # client_order_id -> order_id (idempotency anchor, in-memory only)
        self._orders: dict[str, str] = {}
        self._seq = 0

    async def get_rate(self, base: str, quote: str) -> RateQuote:
        return RateQuote(
            base_asset=base.upper(),
            quote_asset=quote.upper(),
            bid="67250.00",
            ask="67251.00",
            ttl_seconds=5,
            quoted_at="2026-06-12T00:00:00Z",
        )

    async def place_order(self, order: ExchangeOrderRequest) -> OrderResult:
        existing = self._orders.get(order.client_order_id)
        if existing is not None:
            # Idempotent replay: same client_order_id -> original order_id.
            return self._result_for(existing, order)
        self._seq += 1
        order_id = f"mock-{self._seq:06d}"
        self._orders[order.client_order_id] = order_id
        return self._result_for(order_id, order)

    async def cancel_order(self, order_id: str) -> bool:
        # Mock: known orders cancel (True); unknown -> False (idempotent, no error).
        return order_id in self._orders.values()

    async def get_order_status(self, order_id: str) -> OrderResult:
        return OrderResult(
            order_id=order_id,
            state=OrderState.ACCEPTED,
            filled_amount="0",
        )

    @staticmethod
    def _result_for(order_id: str, order: ExchangeOrderRequest) -> OrderResult:
        return OrderResult(
            order_id=order_id,
            state=OrderState.ACCEPTED,
            filled_amount="0",
            raw={"mock": True, "clientOrderId": order.client_order_id},
        )
