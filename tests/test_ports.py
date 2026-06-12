from __future__ import annotations

import asyncio
from decimal import Decimal

from banxe_trading_backend.models import ExchangeOrderRequest, OrderSide, OrderType
from banxe_trading_backend.ports import (
    ExchangePort,
    InMemoryMockExchange,
    InMemoryMockMarketData,
    MarketDataPort,
)


def test_mock_adapters_satisfy_protocols() -> None:
    assert isinstance(InMemoryMockExchange(), ExchangePort)
    assert isinstance(InMemoryMockMarketData(), MarketDataPort)


def test_market_data_snapshot_then_diffs() -> None:
    md = InMemoryMockMarketData()
    snap = asyncio.run(md.get_snapshot("BTC-EUR"))
    assert snap.sequence == 1
    assert snap.bids and snap.asks
    Decimal(snap.bids[0].price)  # decimal string (I-01)

    async def collect() -> list[int]:
        return [d.sequence async for d in md.stream_diffs("BTC-EUR")]

    seqs = asyncio.run(collect())
    assert seqs == [2, 3, 4]
    assert seqs == sorted(seqs)  # strictly increasing


def test_market_data_lists_symbols() -> None:
    md = InMemoryMockMarketData()
    symbols = md.list_symbols()
    assert {s.symbol for s in symbols} >= {"BTC-EUR"}


def test_exchange_place_order_idempotent() -> None:
    ex = InMemoryMockExchange()
    order = ExchangeOrderRequest(
        base_asset="BTC",
        quote_asset="EUR",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        amount="1",
        client_order_id="abc",
        correlation_id="corr",
    )
    first = asyncio.run(ex.place_order(order))
    second = asyncio.run(ex.place_order(order))
    assert first.order_id == second.order_id  # idempotent on client_order_id


def test_exchange_rate_has_positive_ttl() -> None:
    ex = InMemoryMockExchange()
    quote = asyncio.run(ex.get_rate("BTC", "EUR"))
    assert quote.ttl_seconds > 0
    Decimal(quote.bid)
    Decimal(quote.ask)
