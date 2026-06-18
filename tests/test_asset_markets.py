"""M1.13 — asset->markets reverse cross-reference (read-only filter, mock-safe).

characterization: BTC/EUR return matching markets (base or quote), deterministic bundle order +
endpoint 200; contract: frozen DTOs + existing endpoints unchanged; negative/fail-closed: unknown
asset / asset with no markets -> empty list (non-404), no fabrication.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.assets.catalog import CryptoAssetMetadata
from banxe_trading_backend.instruments.xref import (
    InstrumentAssetXref,
    list_instrument_asset_xref,
    markets_for_asset,
)
from banxe_trading_backend.models import InstrumentInfo, SymbolInfo


def test_btc_returns_markets_where_base_or_quote() -> None:
    out = markets_for_asset("BTC")
    assert out  # BTC-EUR present
    assert all(isinstance(x, InstrumentAssetXref) for x in out)
    assert all("BTC" in (x.base_asset.asset, x.quote_asset.asset) for x in out)
    assert "BTC-EUR" in [x.symbol for x in out]


def test_eur_returns_all_quote_markets() -> None:
    out = markets_for_asset("EUR")
    # EUR is quote of every configured market
    assert {x.symbol for x in out} == {x.symbol for x in list_instrument_asset_xref()}


def test_normalization_case_insensitive() -> None:
    lower = [x.symbol for x in markets_for_asset("btc")]
    upper = [x.symbol for x in markets_for_asset("BTC")]
    assert lower == upper


def test_deterministic_order_matches_bundle() -> None:
    bundle_order = [x.symbol for x in list_instrument_asset_xref()]
    eur_order = [x.symbol for x in markets_for_asset("EUR")]
    assert eur_order == [s for s in bundle_order if s in eur_order]


def test_endpoint_200() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/assets/BTC/markets")
    assert r.status_code == 200
    body = r.json()
    assert body and all("BTC" in (b["baseAsset"]["asset"], b["quoteAsset"]["asset"]) for b in body)
    assert "balance" not in r.text.lower() and "posting" not in r.text.lower()


def test_frozen_contracts_unchanged() -> None:
    assert set(InstrumentInfo.model_fields.keys()) == {
        "symbol", "tick_size", "min_qty", "max_qty", "fee_schedule_ref",
    }
    assert set(SymbolInfo.model_fields.keys()) == {
        "symbol", "base_asset", "quote_asset", "price_precision", "qty_precision", "status",
    }
    assert set(CryptoAssetMetadata.model_fields.keys()) == {
        "asset", "name", "asset_class", "networks", "display_decimals", "source",
    }
    assert set(InstrumentAssetXref.model_fields.keys()) == {
        "symbol", "instrument", "base_asset", "quote_asset",
    }


def test_existing_endpoints_unchanged() -> None:
    client = TestClient(create_app())
    for p in (
        "/api/v1/symbols", "/api/v1/instruments", "/api/v1/instruments/BTC-EUR",
        "/api/v1/instruments/BTC-EUR/assets", "/api/v1/markets", "/api/v1/assets/metadata",
    ):
        assert client.get(p).status_code == 200


def test_unknown_asset_empty_list_fail_closed() -> None:
    assert markets_for_asset("DOGE") == []
    client = TestClient(create_app())
    r = client.get("/api/v1/assets/DOGE/markets")
    assert r.status_code == 200 and r.json() == []  # non-404, no fabricated market
