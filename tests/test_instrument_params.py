"""M1.9 — advisory instrument trading-parameters (config-as-data, read-only, mock-safe).

characterization: known symbols return config params (not the old stub); config covers the
SymbolInfo universe; contract: InstrumentInfo + adjacent frozen contracts unchanged, existing
endpoints compatible; negative: unknown symbol -> fail-closed (404 / InstrumentParamsError).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.dse.models import EarnMetrics
from banxe_trading_backend.instruments.params import (
    InstrumentParamsError,
    instrument_info,
)
from banxe_trading_backend.models import InstrumentInfo, SymbolInfo
from banxe_trading_backend.ports.market_data_port import InMemoryMockMarketData


def test_known_symbol_returns_config_not_stub() -> None:
    info = instrument_info("ETH-EUR")
    assert isinstance(info, InstrumentInfo)
    assert info.symbol == "ETH-EUR"
    assert info.min_qty == "0.0010"
    assert info.fee_schedule_ref == "spot-default"  # config, not old stub "default"


def test_symbol_normalization() -> None:
    assert instrument_info("btc/eur").symbol == "BTC-EUR"


def test_config_covers_symbol_universe() -> None:
    for sym in InMemoryMockMarketData().list_symbols():
        assert instrument_info(sym.symbol).symbol == sym.symbol


def test_instrument_endpoint_known_200() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/instruments/BTC-EUR")
    assert r.status_code == 200
    assert r.json()["feeScheduleRef"] == "spot-default"


def test_frozen_contracts_unchanged() -> None:
    assert set(InstrumentInfo.model_fields.keys()) == {
        "symbol", "tick_size", "min_qty", "max_qty", "fee_schedule_ref",
    }
    assert set(SymbolInfo.model_fields.keys()) == {
        "symbol", "base_asset", "quote_asset", "price_precision", "qty_precision", "status",
    }
    assert len(EarnMetrics.model_fields) == 6


def test_existing_endpoints_unchanged() -> None:
    client = TestClient(create_app())
    for p in (
        "/api/v1/symbols", "/api/v1/earn/rates",
        "/api/v1/accounts/metadata", "/api/v1/assets/metadata",
    ):
        assert client.get(p).status_code == 200


def test_unknown_symbol_fail_closed() -> None:
    with pytest.raises(InstrumentParamsError):
        instrument_info("DOGE-EUR")


def test_unknown_symbol_endpoint_404() -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/instruments/DOGE-EUR").status_code == 404
