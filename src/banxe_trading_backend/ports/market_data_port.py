"""MarketDataPort — new read-only L2 depth port (ADR-021 D4).

No order-book/depth feed exists upstream yet, so this port is introduced here
(owned by the trading-backend). Concrete providers implement it behind a
provider-parameterized selection (``MARKET_DATA_PROVIDER``), mirroring the
ExchangePort adapter families. The skeleton ships ``InMemoryMockMarketData``
only — it emits the verbatim FE envelope (snapshot then diffs) with decimal
strings (I-01), so the FE swaps its mock factory for a real WS with no type
change.

TODO(ADR-021 governance): select the real provider (PrimaryExchangeAdapter /
CCXT Pro / aggregator) — licensing, rate limits, coverage, latency, CASS/audit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from banxe_trading_backend.models import (
    RawOrderBookDiff,
    RawOrderBookSnapshot,
    RawPriceLevel,
    SymbolInfo,
)


@runtime_checkable
class MarketDataPort(Protocol):
    """Read-only L2 depth. Drives the WS channel + REST snapshot fallback."""

    async def get_snapshot(self, symbol: str) -> RawOrderBookSnapshot: ...

    def stream_diffs(self, symbol: str) -> AsyncIterator[RawOrderBookDiff]: ...

    def list_symbols(self) -> list[SymbolInfo]: ...


_MOCK_SYMBOLS = [
    SymbolInfo(
        symbol="BTC-EUR",
        base_asset="BTC",
        quote_asset="EUR",
        price_precision=2,
        qty_precision=4,
        status="trading",
    ),
    SymbolInfo(
        symbol="ETH-EUR",
        base_asset="ETH",
        quote_asset="EUR",
        price_precision=2,
        qty_precision=4,
        status="trading",
    ),
]


class InMemoryMockMarketData:
    """Deterministic mock MarketDataPort — NO live feed.

    Emits a fixed snapshot (sequence 1) then a fixed, finite diff sequence
    (2, 3, 4). All prices/quantities are decimal strings (I-01).
    """

    _SNAPSHOT_BIDS = [("67250.50", "1.2500"), ("67249.00", "0.8000")]
    _SNAPSHOT_ASKS = [("67251.00", "0.9000"), ("67252.50", "1.5000")]
    _DIFFS: list[tuple[list[tuple[str, str]], list[tuple[str, str]]]] = [
        ([("67250.50", "0.4000")], []),
        ([], [("67251.00", "0.0000")]),  # quantity 0 -> delete level
        ([("67250.75", "1.0000")], []),
    ]

    async def get_snapshot(self, symbol: str) -> RawOrderBookSnapshot:
        return RawOrderBookSnapshot(
            bids=[RawPriceLevel(price=p, quantity=q) for p, q in self._SNAPSHOT_BIDS],
            asks=[RawPriceLevel(price=p, quantity=q) for p, q in self._SNAPSHOT_ASKS],
            sequence=1,
        )

    async def stream_diffs(self, symbol: str) -> AsyncIterator[RawOrderBookDiff]:
        seq = 1
        for bids, asks in self._DIFFS:
            seq += 1
            yield RawOrderBookDiff(
                bids=[RawPriceLevel(price=p, quantity=q) for p, q in bids],
                asks=[RawPriceLevel(price=p, quantity=q) for p, q in asks],
                sequence=seq,
            )

    def list_symbols(self) -> list[SymbolInfo]:
        return list(_MOCK_SYMBOLS)
