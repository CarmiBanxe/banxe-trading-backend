"""M1.17 — markets breakdown (per-base/per-quote counts, read-only derived, mock-safe).

characterization: by_base/by_quote == group-by over list_instrument_asset_xref, total == len ==
sum(by_base) == sum(by_quote), deterministic order, endpoint 200; contract: frozen DTOs + existing
endpoints unchanged; fail-closed: no fabricated assets, consistent sums.
"""
from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.instruments.xref import InstrumentAssetXref, list_instrument_asset_xref
from banxe_trading_backend.meta.breakdown import (
    CatalogueBreakdown,
    MarketAssetCount,
    MarketsBreakdown,
    markets_breakdown,
)
from banxe_trading_backend.meta.catalogue import CatalogueMeta


def _markets() -> list[InstrumentAssetXref]:
    return list_instrument_asset_xref()


def test_counts_match_group_by() -> None:
    mb = markets_breakdown()
    assert isinstance(mb, MarketsBreakdown)
    exp_base = Counter(m.base_asset.asset for m in _markets())
    exp_quote = Counter(m.quote_asset.asset for m in _markets())
    assert {e.asset: e.count for e in mb.by_base} == dict(exp_base)
    assert {e.asset: e.count for e in mb.by_quote} == dict(exp_quote)
    assert all(isinstance(e, MarketAssetCount) for e in mb.by_base + mb.by_quote)


def test_total_and_sum_consistency() -> None:
    mb = markets_breakdown()
    n = len(_markets())
    assert mb.total == n
    assert sum(e.count for e in mb.by_base) == n
    assert sum(e.count for e in mb.by_quote) == n
    assert mb.source == "sandbox-mock"


def test_deterministic_sorted_order() -> None:
    mb = markets_breakdown()
    assert [e.asset for e in mb.by_base] == sorted(e.asset for e in mb.by_base)
    assert [e.asset for e in mb.by_quote] == sorted(e.asset for e in mb.by_quote)
    assert mb == markets_breakdown()


def test_no_fabricated_assets() -> None:
    mb = markets_breakdown()
    real_base = {m.base_asset.asset for m in _markets()}
    real_quote = {m.quote_asset.asset for m in _markets()}
    assert {e.asset for e in mb.by_base} == real_base
    assert {e.asset for e in mb.by_quote} == real_quote
    assert all(e.count > 0 for e in mb.by_base + mb.by_quote)


def test_endpoint_200_shape() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/markets/breakdown")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"byBase", "byQuote", "total", "source"}
    assert body["total"] == sum(e["count"] for e in body["byBase"])
    assert "apy" not in r.text.lower() and "balance" not in r.text.lower()


def test_frozen_and_existing_endpoints_unchanged() -> None:
    assert set(InstrumentAssetXref.model_fields.keys()) == {
        "symbol", "instrument", "base_asset", "quote_asset",
    }
    assert len(CatalogueMeta.model_fields) == 6
    assert len(CatalogueBreakdown.model_fields) == 3  # breakdown/total/source (unchanged)
    client = TestClient(create_app())
    for p in (
        "/api/v1/markets", "/api/v1/instruments", "/api/v1/symbols",
        "/api/v1/catalogue/meta", "/api/v1/catalogue/breakdown", "/api/v1/earn/taxonomy",
    ):
        assert client.get(p).status_code == 200
