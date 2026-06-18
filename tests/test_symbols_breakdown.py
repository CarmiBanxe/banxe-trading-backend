"""M1.19 — symbols breakdown (by status / precision, read-only derived, mock-safe).

characterization: by_status/by_price_precision/by_qty_precision == group-by over list_symbols;
total==len==sum(each); deterministic order + endpoint 200; contract: frozen DTOs + existing
endpoints unchanged (incl. /symbols not shadowed); fail-closed: no fabricated keys; precision key
is a string; base/quote not re-counted.
"""
from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.meta.breakdown import (
    MarketsBreakdown,
    SymbolDimensionCount,
    SymbolsBreakdown,
    symbols_breakdown,
)
from banxe_trading_backend.models import SymbolInfo
from banxe_trading_backend.ports.market_data_port import InMemoryMockMarketData


def _md() -> InMemoryMockMarketData:
    return InMemoryMockMarketData()


def _syms() -> list[SymbolInfo]:
    return _md().list_symbols()


def test_counts_match_group_by() -> None:
    sb = symbols_breakdown(_md())
    assert isinstance(sb, SymbolsBreakdown)
    assert {e.key: e.count for e in sb.by_status} == dict(Counter(s.status for s in _syms()))
    assert {e.key: e.count for e in sb.by_price_precision} == dict(
        Counter(str(s.price_precision) for s in _syms())
    )
    assert {e.key: e.count for e in sb.by_qty_precision} == dict(
        Counter(str(s.qty_precision) for s in _syms())
    )
    assert all(isinstance(e, SymbolDimensionCount) for e in sb.by_status)


def test_total_and_sum_consistency_all_dims() -> None:
    sb = symbols_breakdown(_md())
    n = len(_syms())
    assert sb.total == n
    assert sum(e.count for e in sb.by_status) == n
    assert sum(e.count for e in sb.by_price_precision) == n
    assert sum(e.count for e in sb.by_qty_precision) == n
    assert sb.source == "sandbox-mock"


def test_precision_key_is_string_and_deterministic() -> None:
    sb = symbols_breakdown(_md())
    assert all(isinstance(e.key, str) for e in sb.by_price_precision + sb.by_qty_precision)
    assert [e.key for e in sb.by_status] == sorted(e.key for e in sb.by_status)
    assert sb == symbols_breakdown(_md())


def test_no_fabricated_keys() -> None:
    sb = symbols_breakdown(_md())
    assert {e.key for e in sb.by_status} == {s.status for s in _syms()}
    assert {e.key for e in sb.by_price_precision} == {str(s.price_precision) for s in _syms()}
    assert all(e.count > 0 for e in sb.by_status + sb.by_price_precision + sb.by_qty_precision)


def test_endpoint_200_shape() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/symbols-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"byStatus", "byPricePrecision", "byQtyPrecision", "total", "source"}
    assert body["total"] == sum(e["count"] for e in body["byStatus"])
    # base/quote NOT re-counted here (owned by markets breakdown)
    assert "byBase" not in body and "byQuote" not in body
    assert "balance" not in r.text.lower() and "apy" not in r.text.lower()


def test_symbols_route_not_shadowed_and_frozen() -> None:
    assert set(SymbolInfo.model_fields.keys()) == {
        "symbol", "base_asset", "quote_asset", "price_precision", "qty_precision", "status",
    }
    assert len(MarketsBreakdown.model_fields) == 4
    client = TestClient(create_app())
    assert client.get("/api/v1/symbols").status_code == 200  # not shadowed
    for p in (
        "/api/v1/catalogue/meta", "/api/v1/catalogue/breakdown",
        "/api/v1/catalogue/instruments-breakdown", "/api/v1/markets/breakdown",
    ):
        assert client.get(p).status_code == 200
