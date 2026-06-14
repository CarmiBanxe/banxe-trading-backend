"""Market-making advisory seam (Sprint S12 / X9.1) — strategy port, mock-only.

A formal strategy abstraction over the existing QuotePort / ExchangePort that
produces an ADVISORY quote ladder around a mid price. Anchored by ADR-083
(Hummingbot as a future strategy *sidecar*, not a port). STRICTLY advisory and
sandbox/mock-only (ADR-089):
  * the ladder rungs are UNSIGNED suggestions — nothing is signed, submitted, or
    executed (the backend holds no keys; the client signs client-side);
  * mock by default, deterministic, no network, no keys, no live venue;
  * non-mock providers fail closed (operator-gated) — no live strategy host.
It composes over QuotePort/ExchangePort WITHOUT changing their semantics and adds
NO new public BaaS endpoint and NO change to /v1/dss/recommend.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from banxe_trading_backend.models import CamelModel, DecimalStr


class MmPreviewRequest(CamelModel):
    asset: str
    mid_price: DecimalStr | None = None  # if absent, derived from the (mock) rate
    spread_bps: int = 10
    levels: int = 3
    size_usd: DecimalStr = "1000"


class MmRung(CamelModel):
    level: int
    side: str  # buy | sell — advisory, unsigned (never executed)
    price: DecimalStr
    size_usd: DecimalStr
    spread_bps: int


class MmPreviewResponse(CamelModel):
    asset: str
    mid: DecimalStr
    mode: str
    signed: bool
    submitted: bool
    rungs: list[MmRung]
    source: str
    disclaimer: str


@runtime_checkable
class MarketMakingPort(Protocol):
    """Advisory market-making strategy — builds an unsigned quote ladder."""

    def build_ladder(
        self, *, asset: str, mid: Decimal, spread_bps: int, levels: int, size_usd: Decimal
    ) -> list[MmRung]: ...


class MockMarketMakingStrategy:
    """Deterministic symmetric ladder around mid — no network, advisory only."""

    def build_ladder(
        self, *, asset: str, mid: Decimal, spread_bps: int, levels: int, size_usd: Decimal
    ) -> list[MmRung]:
        rungs: list[MmRung] = []
        size = str(size_usd)
        for i in range(1, levels + 1):
            cum_bps = spread_bps * i
            offset = mid * Decimal(cum_bps) / Decimal(10000)
            bid = (mid - offset).quantize(Decimal("0.01"))
            ask = (mid + offset).quantize(Decimal("0.01"))
            rungs.append(
                MmRung(level=i, side="buy", price=str(bid), size_usd=size, spread_bps=cum_bps)
            )
            rungs.append(
                MmRung(level=i, side="sell", price=str(ask), size_usd=size, spread_bps=cum_bps)
            )
        return rungs


def build_mm_provider(name: str) -> MarketMakingPort:
    """Resolve a market-making strategy by name. Only 'mock' is wired (default)."""
    if name == "mock":
        return MockMarketMakingStrategy()
    # A live strategy host (e.g. Hummingbot sidecar) is OPERATOR-GATED (ODR).
    raise ValueError(
        f"market-making provider {name!r} is not wired (operator-gated); only 'mock'"
    )
