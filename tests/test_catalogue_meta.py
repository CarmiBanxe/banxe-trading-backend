"""M1.14 — public catalogue meta surface (derived counts + version, read-only, mock-safe).

characterization: counts match the current mock universe + version == __version__; contract:
existing public endpoints unchanged and internal ops endpoints remain unexposed; fail-closed:
derived from existing fail-closed list functions (no fabricated count).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend import __version__
from banxe_trading_backend.app import create_app
from banxe_trading_backend.assets.catalog import asset_catalog
from banxe_trading_backend.instruments.params import list_instruments
from banxe_trading_backend.instruments.xref import list_instrument_asset_xref
from banxe_trading_backend.meta.catalogue import CatalogueMeta, catalogue_meta
from banxe_trading_backend.ports.market_data_port import InMemoryMockMarketData


def _md() -> InMemoryMockMarketData:
    return InMemoryMockMarketData()


def test_counts_match_mock_universe() -> None:
    md = _md()
    meta = catalogue_meta(md)
    assert isinstance(meta, CatalogueMeta)
    assert meta.symbols_count == len(md.list_symbols())
    assert meta.instruments_count == len(list_instruments())
    assert meta.markets_count == len(list_instrument_asset_xref())
    assert meta.assets_count == len(asset_catalog(md).assets)
    assert meta.version == __version__
    assert meta.source == "sandbox-mock"


def test_counts_are_positive_ints() -> None:
    meta = catalogue_meta(_md())
    for v in (meta.symbols_count, meta.instruments_count, meta.markets_count, meta.assets_count):
        assert isinstance(v, int) and v >= 0


def test_endpoint_200_and_shape() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/meta")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "symbolsCount", "instrumentsCount", "marketsCount", "assetsCount", "version", "source",
    }
    assert body["version"] == __version__
    # no money/balance leakage in a meta surface
    assert "balance" not in r.text.lower() and "amount" not in r.text.lower()


def test_single_version_source() -> None:
    # version is exactly the package __version__ (no second version constant)
    assert catalogue_meta(_md()).version == __version__


def test_internal_ops_endpoints_not_in_public_schema() -> None:
    client = TestClient(create_app())
    schema = client.get("/openapi.json").json()
    paths = set(schema.get("paths", {}))
    # the new public meta path is documented...
    assert "/api/v1/catalogue/meta" in paths
    # ...while internal ops endpoints remain fenced out of the public schema
    assert not any(p.startswith("/internal") for p in paths)


def test_existing_public_endpoints_unchanged() -> None:
    client = TestClient(create_app())
    for p in (
        "/api/v1/symbols", "/api/v1/instruments", "/api/v1/markets",
        "/api/v1/assets/metadata", "/api/v1/assets/BTC/markets",
    ):
        assert client.get(p).status_code == 200
