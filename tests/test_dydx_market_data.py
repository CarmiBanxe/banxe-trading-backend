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

    # Default config (mode=mock, market_provider=mock, kill-switch off) → mock.
    app = create_app(Settings())
    assert isinstance(app.state.market_data, InMemoryMockMarketData)


def test_dydx_provider_builds_adapter_without_network() -> None:
    from banxe_trading_backend.app import create_app

    # Full S6.2-EN sandbox-live combo: mode + provider + kill-switch ALL on.
    # Building the dydx provider must NOT open any connection (lazy transport).
    app = create_app(Settings(
        dse_provider_mode="sandbox-live",
        dse_market_provider="dydx",
        dse_live_allowed=True,
    ))
    assert isinstance(app.state.market_data, DydxMarketDataAdapter)


# --------------------------------------------------------------------------- #
# S6.2-EN conformance: flag-gate selection matrix + fail-closed fallback       #
# --------------------------------------------------------------------------- #


def _build_market_data_for(**overrides: object) -> object:
    """Resolve the MarketDataPort the app would build under ``overrides``.

    Constructs Settings with the given DSE overrides (everything else default
    mock) and reads ``app.state.market_data`` after ``create_app``. No network
    is opened — the dydx transport is lazy.
    """
    from banxe_trading_backend.app import create_app

    return create_app(Settings(**overrides)).state.market_data  # type: ignore[arg-type]


def test_selection_full_combo_routes_to_dydx() -> None:
    """All three flags ON → dYdX adapter (the one wired live route)."""
    md = _build_market_data_for(
        dse_provider_mode="sandbox-live",
        dse_market_provider="dydx",
        dse_live_allowed=True,
    )
    assert isinstance(md, DydxMarketDataAdapter)


def test_selection_kill_switch_off_fails_closed_to_mock() -> None:
    """dydx + sandbox-live but kill-switch off → fail-closed to mock (no raise)."""
    md = _build_market_data_for(
        dse_provider_mode="sandbox-live",
        dse_market_provider="dydx",
        dse_live_allowed=False,
    )
    assert isinstance(md, InMemoryMockMarketData)


def test_selection_mode_mock_routes_to_mock_even_with_kill_switch_on() -> None:
    """mode=mock dominates: even with kill-switch on + dydx, stays on mock."""
    md = _build_market_data_for(
        dse_provider_mode="mock",
        dse_market_provider="dydx",
        dse_live_allowed=True,
    )
    assert isinstance(md, InMemoryMockMarketData)


def test_selection_provider_mock_routes_to_mock() -> None:
    """sandbox-live + kill-switch but provider=mock → mock (kept on default)."""
    md = _build_market_data_for(
        dse_provider_mode="sandbox-live",
        dse_market_provider="mock",
        dse_live_allowed=True,
    )
    assert isinstance(md, InMemoryMockMarketData)


def test_selection_defaults_route_to_mock() -> None:
    """The shipped default config routes to the in-memory mock (CI-safe)."""
    md = _build_market_data_for()
    assert isinstance(md, InMemoryMockMarketData)


def test_dydx_adapter_uses_dse_market_base_url_when_set() -> None:
    """config-as-data: BANXE_DSE_MARKET_BASE_URL overrides the default REST host."""
    from banxe_trading_backend.app import create_app
    from banxe_trading_backend.ports.dydx_market_data import HttpxWebsocketsTransport

    settings = Settings(
        dse_provider_mode="sandbox-live",
        dse_market_provider="dydx",
        dse_live_allowed=True,
        dse_market_base_url="https://indexer.example.test/v4",
    )
    md = create_app(settings).state.market_data
    assert isinstance(md, DydxMarketDataAdapter)
    transport = md._transport  # noqa: SLF001 — verifying config-as-data wiring
    assert isinstance(transport, HttpxWebsocketsTransport)
    assert transport._rest_url == "https://indexer.example.test/v4"  # noqa: SLF001


def test_dydx_adapter_falls_back_to_built_in_rest_url_when_dse_base_url_empty() -> None:
    """No ``dse_market_base_url`` set → use the public dYdX Indexer default."""
    from banxe_trading_backend.app import create_app
    from banxe_trading_backend.ports.dydx_market_data import HttpxWebsocketsTransport

    settings = Settings(
        dse_provider_mode="sandbox-live",
        dse_market_provider="dydx",
        dse_live_allowed=True,
    )
    md = create_app(settings).state.market_data
    assert isinstance(md, DydxMarketDataAdapter)
    transport = md._transport  # noqa: SLF001
    assert isinstance(transport, HttpxWebsocketsTransport)
    assert transport._rest_url == "https://indexer.dydx.trade/v4"  # noqa: SLF001


# --- Fail-closed on provider error: a failing dydx transport must surface --- #
# Below we use the adapter directly to assert error semantics at the I/O seam.


class _FailingTransport:
    """A DydxIndexerTransport that raises on every call (simulates outage)."""

    async def fetch_orderbook(self, ticker: str) -> Mapping[str, object]:
        raise ConnectionError("simulated dYdX Indexer outage")

    async def stream_orderbook(
        self, ticker: str
    ) -> AsyncIterator[Mapping[str, object]]:
        raise ConnectionError("simulated dYdX Indexer outage")
        yield {}  # pragma: no cover — unreachable; satisfies AsyncIterator typing


def test_provider_error_surfaces_at_io_seam() -> None:
    """The adapter does NOT swallow transport errors silently; the WS handler
    above the port is responsible for the mock fallback. Asserts the error is
    raised at the I/O seam so the host-level fail-closed can detect & re-route.
    """
    import pytest

    adapter = DydxMarketDataAdapter(_FailingTransport())  # type: ignore[arg-type]
    with pytest.raises(ConnectionError):
        asyncio.run(adapter.get_snapshot("BTC-USD"))


def test_resolver_helper_returns_dydx_only_under_full_combo() -> None:
    """Direct unit test of the resolver: dydx iff all three flags ON, else mock."""
    from banxe_trading_backend.dse import resolve_market_data_route

    ON = {
        "dse_provider_mode": "sandbox-live",
        "dse_market_provider": "dydx",
        "dse_live_allowed": True,
    }
    assert resolve_market_data_route(Settings(**ON)) == "dydx"
    # Drop any single flag → fall back to mock.
    for drop in ON:
        partial = {k: v for k, v in ON.items() if k != drop}
        assert resolve_market_data_route(Settings(**partial)) == "mock", drop
    # Mock everything (default) → mock.
    assert resolve_market_data_route(Settings()) == "mock"


def test_decimal_validation_rejects_floats_in_diffs_too() -> None:
    """I-01 reinforces: floats are rejected at the boundary in BOTH paths."""
    import pytest

    # Snapshot path already covered by test_decimal_fidelity_rejects_float_i01.
    # Confirm the diff path also rejects a float in a [price, size] pair.
    with pytest.raises(TypeError):
        map_batch_update([{"bids": [[100.0, "1.0"]]}], sequence=1)
    with pytest.raises(TypeError):
        map_batch_update([{"asks": [["100.0", 1.0]]}], sequence=1)
