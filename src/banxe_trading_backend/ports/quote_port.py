"""QuotePort — aggregator/RFQ quotes (ADR-083 D3; S6.5).

A read-only port for spot / cross-chain swap *quotes* (distinct from the
order-book ExchangePort). The default provider is a deterministic in-memory mock
(no network) so CI/dev are safe; the LI.FI adapter activates only via env
(``BANXE_QUOTE_PROVIDER=lifi``). Self-custodial: a quote is an estimate; any
resulting transaction is signed by the client wallet, never the backend.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from banxe_trading_backend.models import QuoteRequest, QuoteResponse


@runtime_checkable
class QuotePort(Protocol):
    """Return a normalized quote for a (cross-chain) swap."""

    async def get_quote(self, request: QuoteRequest) -> QuoteResponse: ...


class MockQuoteAdapter:
    """Deterministic in-memory QuotePort — NO network. Default for CI/dev.

    Returns a stub quote derived from the request (estimated return = amount
    minus a fixed 1% notional), so behaviour is fully reproducible.
    """

    _RETURN_FACTOR = Decimal("0.99")  # stub: 1% notional cost
    _SLIPPAGE = "0.005"

    async def get_quote(self, request: QuoteRequest) -> QuoteResponse:
        amount = Decimal(request.amount)
        estimated = int(amount * self._RETURN_FACTOR)  # atomic units, integer
        return QuoteResponse(
            from_chain=request.from_chain,
            to_chain=request.to_chain,
            from_token=request.from_token,
            to_token=request.to_token,
            amount=request.amount,
            estimated_return=str(estimated),
            estimated_return_min=str(int(amount * Decimal("0.985"))),
            slippage=request.slippage or self._SLIPPAGE,
            provider="mock",
            hops=1,
            route={"tool": "mock", "steps": 1},
        )
