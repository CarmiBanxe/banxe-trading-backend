"""M1.11 — instrument<->asset cross-reference advisory view (composition, read-only, mock-safe).

characterization: known symbols compose instrument + base/quote asset metadata; contract: frozen
DTOs + existing endpoints unchanged; negative: unknown symbol -> 404 / InstrumentParamsError.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.assets.catalog import CryptoAssetMetadata
from banxe_trading_backend.instruments.params import InstrumentParamsError, instrument_info
from banxe_trading_backend.instruments.xref import (
    InstrumentAssetXref,
    instrument_asset_xref,
)
from banxe_trading_backend.models import InstrumentInfo, SymbolInfo


def test_xref_composes_known_symbol() -> None:
    x = instrument_asset_xref("BTC-EUR")
    assert isinstance(x, InstrumentAssetXref)
    assert x.symbol == "BTC-EUR"
    assert isinstance(x.instrument, InstrumentInfo) and x.instrument.symbol == "BTC-EUR"
    assert isinstance(x.base_asset, CryptoAssetMetadata) and x.base_asset.asset == "BTC"
    assert isinstance(x.quote_asset, CryptoAssetMetadata) and x.quote_asset.asset == "EUR"
    # reuses M1.9 instrument source (same InstrumentInfo as /instruments/{symbol})
    assert x.instrument == instrument_info("BTC-EUR")


@pytest.mark.parametrize(
    "symbol,base,quote", [("BTC-EUR", "BTC", "EUR"), ("ETH-EUR", "ETH", "EUR")]
)
def test_xref_base_quote_mapping(symbol: str, base: str, quote: str) -> None:
    x = instrument_asset_xref(symbol)
    assert x.base_asset.asset == base
    assert x.quote_asset.asset == quote


def test_xref_endpoint_200() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/instruments/BTC-EUR/assets")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "BTC-EUR"
    assert body["baseAsset"]["asset"] == "BTC"
    assert body["quoteAsset"]["asset"] == "EUR"
    assert body["instrument"]["feeScheduleRef"] == "spot-default"
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


def test_existing_endpoints_unchanged() -> None:
    client = TestClient(create_app())
    for p in (
        "/api/v1/symbols", "/api/v1/instruments", "/api/v1/instruments/BTC-EUR",
        "/api/v1/assets/metadata",
    ):
        assert client.get(p).status_code == 200


def test_unknown_symbol_fail_closed() -> None:
    with pytest.raises(InstrumentParamsError):
        instrument_asset_xref("DOGE-EUR")
    client = TestClient(create_app())
    assert client.get("/api/v1/instruments/DOGE-EUR/assets").status_code == 404
