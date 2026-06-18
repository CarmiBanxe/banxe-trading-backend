"""M1.21 — network breakdown (flatten asset networks, read-only derived, mock-safe).

characterization: by_network == flatten group-by over asset_catalog().assets[*].networks;
total_assets == len(assets); total_memberships == sum(counts); EXPLICIT flatten semantics test
(multi-network -> N buckets, empty-networks -> none, sum != total_assets); deterministic order +
endpoint 200; contract: frozen DTOs + existing endpoints unchanged; fail-closed: empty-networks
asset creates no bucket, no fabricated network key.
"""
from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.assets.catalog import CryptoAssetMetadata, asset_catalog
from banxe_trading_backend.meta.breakdown import (
    NetworkBreakdown,
    NetworkCount,
    network_breakdown,
)
from banxe_trading_backend.ports.market_data_port import InMemoryMockMarketData


def _md() -> InMemoryMockMarketData:
    return InMemoryMockMarketData()


def _assets() -> list[CryptoAssetMetadata]:
    return asset_catalog(_md()).assets


def _flat_expected() -> Counter[str]:
    c: Counter[str] = Counter()
    for a in _assets():
        c.update(a.networks)
    return c


def test_counts_match_flatten_group_by() -> None:
    nb = network_breakdown(_md())
    assert isinstance(nb, NetworkBreakdown)
    assert {e.network: e.count for e in nb.by_network} == dict(_flat_expected())
    assert all(isinstance(e, NetworkCount) for e in nb.by_network)


def test_totals_and_flatten_semantics() -> None:
    nb = network_breakdown(_md())
    assets = _assets()
    assert nb.total_assets == len(assets)
    assert nb.total_memberships == sum(e.count for e in nb.by_network)
    assert nb.total_memberships == sum(len(a.networks) for a in assets)
    # EXPLICIT flatten semantics: with empty-networks assets present, sum(counts) != total_assets
    n_empty = sum(1 for a in assets if not a.networks)
    if n_empty:
        assert nb.total_memberships != nb.total_assets
    assert nb.source == "sandbox-mock"


def test_empty_networks_asset_creates_no_bucket() -> None:
    # fiat assets (empty networks) must not appear as a fabricated network key
    nb = network_breakdown(_md())
    keys = {e.network for e in nb.by_network}
    assert "" not in keys and "unknown" not in keys and "none" not in keys
    assert all(e.count > 0 for e in nb.by_network)
    assert keys == set(_flat_expected())  # only real networks


def test_deterministic_sorted_order() -> None:
    nb = network_breakdown(_md())
    assert [e.network for e in nb.by_network] == sorted(e.network for e in nb.by_network)
    assert nb == network_breakdown(_md())


def test_endpoint_200_shape() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/network-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"byNetwork", "totalAssets", "totalMemberships", "source"}
    assert body["totalMemberships"] == sum(e["count"] for e in body["byNetwork"])
    assert "balance" not in r.text.lower() and "apy" not in r.text.lower()


def test_frozen_and_existing_endpoints_unchanged() -> None:
    assert set(CryptoAssetMetadata.model_fields.keys()) == {
        "asset", "name", "asset_class", "networks", "display_decimals", "source",
    }
    client = TestClient(create_app())
    for p in (
        "/api/v1/assets/metadata", "/api/v1/catalogue/meta", "/api/v1/catalogue/breakdown",
        "/api/v1/catalogue/instruments-breakdown", "/api/v1/catalogue/symbols-breakdown",
        "/api/v1/catalogue/accounts-breakdown",
    ):
        assert client.get(p).status_code == 200


def test_count_equals_assets_containing_network() -> None:
    # Contract: count == #ASSETS listing the network (dedupe per asset); M1.21/M1.23 align.
    nb = network_breakdown(_md())
    assets = _assets()
    for e in nb.by_network:
        containing = sum(1 for a in assets if e.network in set(a.networks))
        assert e.count == containing
        assert e.count <= nb.total_assets


def test_duplicate_network_not_double_counted(monkeypatch) -> None:
    # Synthetic asset listing a duplicate network must count once (dedup-per-entity).
    from types import SimpleNamespace

    import banxe_trading_backend.meta.breakdown as bd

    fake = SimpleNamespace(assets=[SimpleNamespace(networks=["dup", "dup", "solo"])])
    monkeypatch.setattr(bd, "asset_catalog", lambda _md: fake)
    nb = bd.network_breakdown(_md())
    counts = {e.network: e.count for e in nb.by_network}
    assert counts == {"dup": 1, "solo": 1}  # dup NOT counted twice
    assert nb.total_assets == 1
    assert nb.total_memberships == 2
