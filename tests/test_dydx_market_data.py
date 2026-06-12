"""dYdX MarketDataPort adapter — maps the public Indexer stream onto §D2.

No network: a RecordedTransport replays a CAPTURED dYdX `v4_orderbook` batched
sample (REST snapshot + WS subscribed + channel_batch_data updates) shaped per
`dydxprotocol/v4-chain` indexer types. Asserts the adapter emits the exact §D2
envelope the FE already validated in IL-195.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from decimal import Decimal

from banxe_trading_backend.config import Settings
from banxe_trading_backend.models import RawOrderBookDiff, RawOrderBookSnapshot
from banxe_trading_backend.ports import (
    DydxMarketDataAdapter,
    InMemoryMockMarketData,
    MarketDataPort,
)
from banxe_trading_backend.ports.dydx_market_data import map_batch_update, map_snapshot

# --- CAPTURED dYdX Indexer sample (shape per comlink/postgres types) --------- #
# REST snapshot: OrderbookResponseObject {bids/asks: [{price,size}]}
DYDX_REST_SNAPSHOT: Mapping[str, object] = {
    "bids": [
        {"price": "67250.50", "size": "1.2500"},
        {"price": "67249.00", "size": "0.8000"},
    ],
    "asks": [
        {"price": "67251.00", "size": "0.9000"},
        {"price": "67252.50", "size": "1.5000"},
    ],
}
# WS frames: `subscribed` (snapshot, skipped) then batched `channel_batch_data`
# whose contents is a list of {bids?/asks?: [[price, size]]}; size "0" = delete.
DYDX_WS_FRAMES: list[Mapping[str, object]] = [
    {"type": "subscribed", "channel": "v4_orderbook", "contents": DYDX_REST_SNAPSHOT},
    {"type": "channel_batch_data", "contents": [{"bids": [["67250.50", "0.4000"]]}]},
    {"type": "channel_batch_data", "contents": [{"asks": [["67251.00", "0"]]}]},
    {"type": "channel_batch_data", "contents": [{"bids": [["67250.75", "1.0000"]]}]},
]


class RecordedTransport:
    """Replays a captured sample — satisfies DydxIndexerTransport, no network."""

    def __init__(self, snapshot: Mapping[str, object], frames: list[Mapping[str, object]]) -> None:
        self._snapshot = snapshot
        self._frames = frames

    async def fetch_orderbook(self, ticker: str) -> Mapping[str, object]:
        return self._snapshot

    async def stream_orderbook(self, ticker: str) -> AsyncIterator[Mapping[str, object]]:
        for frame in self._frames:
            yield frame


def _levels(side: list) -> list[tuple[str, str]]:
    return [(lvl.price, lvl.quantity) for lvl in side]


def _decimal_levels(side: list) -> list[tuple[Decimal, Decimal]]:
    return [(Decimal(lvl.price), Decimal(lvl.quantity)) for lvl in side]


async def _collect_diffs(adapter: DydxMarketDataAdapter) -> list[RawOrderBookDiff]:
    return [d async for d in adapter.stream_diffs("BTC-USD")]


def test_adapter_satisfies_marketdataport_protocol() -> None:
    adapter = DydxMarketDataAdapter(RecordedTransport(DYDX_REST_SNAPSHOT, DYDX_WS_FRAMES))
    assert isinstance(adapter, MarketDataPort)


def test_snapshot_maps_to_d2() -> None:
    adapter = DydxMarketDataAdapter(RecordedTransport(DYDX_REST_SNAPSHOT, DYDX_WS_FRAMES))
    snap: RawOrderBookSnapshot = asyncio.run(adapter.get_snapshot("BTC-USD"))
    assert snap.sequence == 1
    assert _levels(snap.bids) == [("67250.50", "1.2500"), ("67249.00", "0.8000")]
    assert _levels(snap.asks) == [("67251.00", "0.9000"), ("67252.50", "1.5000")]


def test_full_stream_produces_il195_d2_envelope() -> None:
    """Captured dYdX sample → the exact §D2 sequence the FE validated (IL-195)."""
    adapter = DydxMarketDataAdapter(RecordedTransport(DYDX_REST_SNAPSHOT, DYDX_WS_FRAMES))
    snap = asyncio.run(adapter.get_snapshot("BTC-USD"))
    diffs = asyncio.run(_collect_diffs(adapter))

    assert snap.sequence == 1
    assert [d.sequence for d in diffs] == [2, 3, 4]  # monotonic

    # diff 2: bid 67250.50 -> 0.4000
    assert _decimal_levels(diffs[0].bids) == [(Decimal("67250.50"), Decimal("0.4000"))]
    assert diffs[0].asks == []
    # diff 3: ask 67251.00 deleted (size 0 preserved as quantity 0)
    assert diffs[1].bids == []
    assert _decimal_levels(diffs[1].asks) == [(Decimal("67251.00"), Decimal("0"))]
    assert Decimal(diffs[1].asks[0].quantity) == 0  # delete semantics (§D2 qty 0)
    # diff 4: bid 67250.75 added
    assert _decimal_levels(diffs[2].bids) == [(Decimal("67250.75"), Decimal("1.0000"))]


def test_level_delete_is_size_zero() -> None:
    diff = map_batch_update([{"asks": [["100.0", "0"]]}], sequence=5)
    assert diff.asks[0].quantity == "0"
    assert Decimal(diff.asks[0].quantity).is_zero()


def test_non_batched_contents_object_is_handled() -> None:
    # channel_data (non-batched): contents is a single object, not a list.
    diff = map_batch_update({"bids": [["100.0", "2.0"]]}, sequence=7)
    assert diff.sequence == 7
    assert _levels(diff.bids) == [("100.0", "2.0")]


def test_decimal_fidelity_rejects_float_i01() -> None:
    import pytest

    # A JSON float (not a decimal string) must be rejected at the boundary.
    with pytest.raises(TypeError):
        map_snapshot({"bids": [{"price": 67250.5, "size": "1.0"}], "asks": []}, sequence=1)


def test_sequences_strictly_increasing_across_reconnect() -> None:
    # Stream with a mid-stream re-`subscribed` (reconnect): snapshots are skipped,
    # emitted diff sequences stay strictly increasing (no stale/out-of-order).
    frames: list[Mapping[str, object]] = [
        {"type": "subscribed", "contents": DYDX_REST_SNAPSHOT},
        {"type": "channel_batch_data", "contents": [{"bids": [["1", "1"]]}]},
        {"type": "subscribed", "contents": DYDX_REST_SNAPSHOT},  # reconnect snapshot
        {"type": "channel_batch_data", "contents": [{"asks": [["2", "2"]]}]},
        {"type": "channel_batch_data", "contents": [{"bids": [["3", "0"]]}]},
    ]
    adapter = DydxMarketDataAdapter(RecordedTransport(DYDX_REST_SNAPSHOT, frames))
    diffs = asyncio.run(_collect_diffs(adapter))
    seqs = [d.sequence for d in diffs]
    assert seqs == [1, 2, 3]
    assert all(b > a for a, b in zip(seqs, seqs[1:], strict=False))  # strictly increasing


def test_list_symbols_returns_dydx_markets() -> None:
    adapter = DydxMarketDataAdapter(RecordedTransport(DYDX_REST_SNAPSHOT, DYDX_WS_FRAMES))
    assert {s.symbol for s in adapter.list_symbols()} >= {"BTC-USD"}


def test_mock_is_default_provider() -> None:
    from banxe_trading_backend.app import create_app

    app = create_app(Settings(market_data_provider="mock"))
    assert isinstance(app.state.market_data, InMemoryMockMarketData)


def test_dydx_provider_builds_adapter_without_network() -> None:
    from banxe_trading_backend.app import create_app

    # Building the dydx provider must NOT open any connection (lazy transport).
    app = create_app(Settings(market_data_provider="dydx"))
    assert isinstance(app.state.market_data, DydxMarketDataAdapter)
