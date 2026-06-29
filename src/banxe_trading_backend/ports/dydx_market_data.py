"""dYdX v4 Indexer adapter for MarketDataPort (ADR-083 MVP step 1, S6.2).

**API-ONLY (AGPL):** dYdX v4 is AGPL-3.0. We consume the *public* dYdX Indexer
over the network (REST + the `v4_orderbook` WebSocket) using generic HTTP/WS
libraries. **No dYdX/AGPL code is vendored or self-hosted** — only the public API
is called. dYdX market data is public, so **no API keys / secrets / wallet** are
needed for this read-only step (execution + integrator keys come later, gated).

Mapping (dYdX Indexer → our §D2 envelope), proof from
`dydxprotocol/v4-chain` indexer comlink/postgres types:

  REST snapshot  `GET /orderbooks/perpetualMarket/{ticker}`
                 → `OrderbookResponseObject {bids:[{price,size}], asks:[...]}`
  WS `subscribed`.contents  → same object form (skipped here; REST seeds snapshot)
  WS `channel_(batch_)data`.contents
                 → `OrderbookMessageContents {bids?:[[price,size]], asks?:[...]}`
                   (batched ⇒ a *list* of these); `size == "0"` deletes a level.

  dYdX `price` → §D2 `price`   ;  dYdX `size` → §D2 `quantity`  (size "0" kept = delete)

The §D2 contract is UNCHANGED. dYdX has no per-message sequence on this channel,
so the adapter **synthesizes a strictly-increasing `sequence`** (snapshot, then a
+1 per emitted diff) — satisfying §D2's monotonic-sequence rule (the FE store
drops any `diff.sequence <= snapshot.sequence`). The Indexer already exposes
human-readable **decimal strings** (not raw quantums), so the boundary work is to
**validate each value parses as Decimal (I-01, never float)** and pass it through;
this is the seam where any raw quantum/subtick→Decimal conversion would live.

TODO(S6.7 hardening): re-snapshot on WS reconnect/gap; markets refresh for
list_symbols; buffer updates between REST snapshot and WS subscribe.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from banxe_trading_backend.models import (
    RawOrderBookDiff,
    RawOrderBookSnapshot,
    RawPriceLevel,
    SymbolInfo,
)

if TYPE_CHECKING:
    from banxe_trading_backend.config import Settings

_DYDX_SUBSCRIBE_BATCHED = True


# --------------------------------------------------------------------------- #
# Boundary: validate dYdX decimal strings (I-01 — never float)                 #
# --------------------------------------------------------------------------- #


def _to_decimal_str(value: object) -> str:
    """Validate a dYdX price/size is a Decimal-parseable string (I-01)."""
    if not isinstance(value, str):
        raise TypeError(
            f"dYdX value must be a decimal string (I-01), got {type(value).__name__}"
        )
    try:
        Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid dYdX decimal string: {value!r}") from exc
    return value


def _level_from_object(obj: object) -> RawPriceLevel:
    """Snapshot level: dYdX `OrderbookResponsePriceLevel {price, size}`."""
    if not isinstance(obj, Mapping):
        raise TypeError(f"expected dYdX object level, got {type(obj).__name__}")
    return RawPriceLevel(
        price=_to_decimal_str(obj["price"]),
        quantity=_to_decimal_str(obj["size"]),
    )


def _level_from_pair(pair: object) -> RawPriceLevel:
    """Update level: dYdX `PriceLevel = [price, size]`."""
    if not isinstance(pair, Sequence) or isinstance(pair, str | bytes) or len(pair) < 2:
        raise TypeError("expected dYdX [price, size] pair")
    return RawPriceLevel(
        price=_to_decimal_str(pair[0]),
        quantity=_to_decimal_str(pair[1]),
    )


# --------------------------------------------------------------------------- #
# Pure mapping: dYdX contents → §D2 envelope                                   #
# --------------------------------------------------------------------------- #


def map_snapshot(contents: Mapping[str, object], sequence: int) -> RawOrderBookSnapshot:
    """Map a dYdX `OrderbookResponseObject` → §D2 snapshot."""
    bids = [_level_from_object(b) for b in _as_list(contents.get("bids"))]
    asks = [_level_from_object(a) for a in _as_list(contents.get("asks"))]
    return RawOrderBookSnapshot(bids=bids, asks=asks, sequence=sequence)


def map_batch_update(contents: object, sequence: int) -> RawOrderBookDiff:
    """Map a dYdX `channel_(batch_)data` contents → one §D2 diff.

    Batched contents is a list of `OrderbookMessageContents`; non-batched is a
    single object. Elements are coalesced last-write-wins per price per side, so
    a batch becomes one atomic §D2 diff. `size "0"` is preserved (= delete).
    """
    batch = contents if isinstance(contents, list) else [contents]
    bid_levels: dict[str, RawPriceLevel] = {}
    ask_levels: dict[str, RawPriceLevel] = {}
    for element in batch:
        if not isinstance(element, Mapping):
            continue
        for pair in _as_list(element.get("bids")):
            lvl = _level_from_pair(pair)
            bid_levels[lvl.price] = lvl
        for pair in _as_list(element.get("asks")):
            lvl = _level_from_pair(pair)
            ask_levels[lvl.price] = lvl
    return RawOrderBookDiff(
        bids=list(bid_levels.values()),
        asks=list(ask_levels.values()),
        sequence=sequence,
    )


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


# --------------------------------------------------------------------------- #
# Transport (injectable) — real impl consumes the PUBLIC Indexer (no secrets)  #
# --------------------------------------------------------------------------- #


@runtime_checkable
class DydxIndexerTransport(Protocol):
    """Public dYdX Indexer transport. Injectable so CI replays fixtures."""

    async def fetch_orderbook(self, ticker: str) -> Mapping[str, object]: ...

    def stream_orderbook(self, ticker: str) -> AsyncIterator[Mapping[str, object]]: ...


class HttpxWebsocketsTransport:
    """Real transport over the PUBLIC dYdX Indexer (REST + WS) with backoff.

    No credentials: dYdX market data is public. Never instantiated in CI.
    """

    _BASE_BACKOFF_S = 1.0
    _MAX_BACKOFF_S = 30.0

    def __init__(self, rest_url: str, ws_url: str) -> None:
        self._rest_url = rest_url.rstrip("/")
        self._ws_url = ws_url

    async def fetch_orderbook(self, ticker: str) -> Mapping[str, object]:
        import httpx  # local import: only needed when the live transport runs

        async with httpx.AsyncClient(base_url=self._rest_url, timeout=10.0) as client:
            resp = await client.get(f"/orderbooks/perpetualMarket/{ticker}")
            resp.raise_for_status()
            data: Mapping[str, object] = resp.json()
            return data

    async def stream_orderbook(self, ticker: str) -> AsyncIterator[Mapping[str, object]]:
        import websockets  # local import: only needed when the live transport runs

        subscribe = json.dumps(
            {
                "type": "subscribe",
                "channel": "v4_orderbook",
                "id": ticker,
                "batched": _DYDX_SUBSCRIBE_BATCHED,
            }
        )
        attempt = 0
        while True:
            try:
                async with websockets.connect(self._ws_url) as ws:
                    await ws.send(subscribe)
                    attempt = 0
                    async for raw in ws:
                        frame: Mapping[str, object] = json.loads(raw)
                        yield frame
            except (OSError, websockets.exceptions.WebSocketException):
                delay = min(self._BASE_BACKOFF_S * 2**attempt, self._MAX_BACKOFF_S)
                attempt += 1
                await asyncio.sleep(delay)


# --------------------------------------------------------------------------- #
# Adapter                                                                      #
# --------------------------------------------------------------------------- #

_DEFAULT_DYDX_SYMBOLS = [
    SymbolInfo(
        symbol="BTC-USD",
        base_asset="BTC",
        quote_asset="USD",
        price_precision=0,
        qty_precision=4,
        status="trading",
    ),
    SymbolInfo(
        symbol="ETH-USD",
        base_asset="ETH",
        quote_asset="USD",
        price_precision=1,
        qty_precision=3,
        status="trading",
    ),
]

# dYdX update frame types that carry order-book deltas.
_DELTA_TYPES = frozenset({"channel_data", "channel_batch_data"})


class DydxMarketDataAdapter:
    """MarketDataPort backed by the public dYdX v4 Indexer (API-only)."""

    def __init__(
        self,
        transport: DydxIndexerTransport,
        symbols: list[SymbolInfo] | None = None,
    ) -> None:
        self._transport = transport
        self._symbols = symbols if symbols is not None else list(_DEFAULT_DYDX_SYMBOLS)
        self._sequence = 0

    @classmethod
    def from_settings(cls, settings: Settings) -> DydxMarketDataAdapter:
        # S6.2-EN config-as-data: BANXE_DSE_MARKET_BASE_URL is the operator-facing
        # override for the dYdX public Indexer base; empty falls back to the
        # built-in mainnet default. WS URL stays its own seam (no DSE flag for it,
        # public Indexer naming is fixed). NO API key — dYdX market data is public.
        rest_url = settings.dse_market_base_url or settings.dydx_indexer_rest_url
        transport = HttpxWebsocketsTransport(
            rest_url=rest_url,
            ws_url=settings.dydx_indexer_ws_url,
        )
        return cls(transport)

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    async def get_snapshot(self, symbol: str) -> RawOrderBookSnapshot:
        contents = await self._transport.fetch_orderbook(self._ticker(symbol))
        return map_snapshot(contents, self._next_sequence())

    async def stream_diffs(self, symbol: str) -> AsyncIterator[RawOrderBookDiff]:
        async for frame in self._transport.stream_orderbook(self._ticker(symbol)):
            if frame.get("type") in _DELTA_TYPES:
                yield map_batch_update(frame.get("contents"), self._next_sequence())
            # `subscribed` / `connected` / `unsubscribed` frames carry no delta.

    def list_symbols(self) -> list[SymbolInfo]:
        return list(self._symbols)

    @staticmethod
    def _ticker(symbol: str) -> str:
        # Our symbol already matches the dYdX perpetual ticker (e.g. "BTC-USD").
        return symbol
