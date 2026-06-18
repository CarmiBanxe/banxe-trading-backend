"""M1.16 — catalogue breakdown (asset-class counts, read-only derived, mock-safe).

characterization: grouped counts from the mock universe, deterministic ordering, total==sum +
endpoint 200; contract: frozen CatalogueMeta + existing endpoints unchanged; fail-closed: no
fabricated class (every class is from an actual catalogued asset).
"""
from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.assets.catalog import asset_catalog
from banxe_trading_backend.meta.breakdown import (
    AssetClassCount,
    CatalogueBreakdown,
    catalogue_breakdown,
)
from banxe_trading_backend.meta.catalogue import CatalogueMeta
from banxe_trading_backend.ports.market_data_port import InMemoryMockMarketData


def _md() -> InMemoryMockMarketData:
    return InMemoryMockMarketData()


def _expected() -> Counter[str]:
    return Counter(a.asset_class for a in asset_catalog(_md()).assets)


def test_grouped_counts_match_catalogue() -> None:
    bd = catalogue_breakdown(_md())
    assert isinstance(bd, CatalogueBreakdown)
    got = {e.asset_class: e.count for e in bd.breakdown}
    assert got == dict(_expected())
    assert all(isinstance(e, AssetClassCount) for e in bd.breakdown)


def test_total_equals_sum_and_asset_count() -> None:
    bd = catalogue_breakdown(_md())
    assert bd.total == sum(e.count for e in bd.breakdown)
    assert bd.total == len(asset_catalog(_md()).assets)
    assert bd.source == "sandbox-mock"


def test_deterministic_canonical_ordering() -> None:
    bd = catalogue_breakdown(_md())
    present = [c for c in ("crypto", "stablecoin", "fiat") if c in dict(_expected())]
    assert [e.asset_class for e in bd.breakdown][: len(present)] == present
    assert bd == catalogue_breakdown(_md())  # deterministic


def test_no_fabricated_class() -> None:
    bd = catalogue_breakdown(_md())
    actual = set(_expected())
    assert {e.asset_class for e in bd.breakdown} == actual  # only real classes, none invented
    assert all(e.count > 0 for e in bd.breakdown)


def test_endpoint_200_shape() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/breakdown")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"breakdown", "total", "source"}
    assert body["total"] == sum(e["count"] for e in body["breakdown"])
    assert "balance" not in r.text.lower() and "apy" not in r.text.lower()


def test_catalogue_meta_unchanged() -> None:
    # M1.14 CatalogueMeta kept frozen — not enriched in place
    assert set(CatalogueMeta.model_fields.keys()) == {
        "symbols_count", "instruments_count", "markets_count", "assets_count", "version", "source",
    }
    client = TestClient(create_app())
    assert client.get("/api/v1/catalogue/meta").status_code == 200


def test_existing_endpoints_unchanged() -> None:
    client = TestClient(create_app())
    for p in (
        "/api/v1/symbols", "/api/v1/instruments", "/api/v1/markets",
        "/api/v1/assets/metadata", "/api/v1/earn/taxonomy",
    ):
        assert client.get(p).status_code == 200
