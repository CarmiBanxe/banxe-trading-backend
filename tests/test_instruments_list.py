"""M1.10 — advisory instruments list/catalogue (additive, read-only, config-as-data, mock-safe).

characterization: deterministic list from the M1.9 single source + endpoint 200; contract:
frozen DTOs/ports + existing /symbols and /instruments/{symbol} unchanged; negative: fail-closed
(malformed config entry skipped, never fabricated).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.instruments import params as iparams
from banxe_trading_backend.instruments.params import instrument_info, list_instruments
from banxe_trading_backend.models import InstrumentInfo, SymbolInfo
from banxe_trading_backend.ports.fee_engine_port import FeeEnginePort
from banxe_trading_backend.ports.market_data_port import MarketDataPort

# ---- characterization ------------------------------------------------------------

def test_list_instruments_deterministic_from_single_source() -> None:
    items = list_instruments()
    assert items == list_instruments()  # deterministic
    symbols = [i.symbol for i in items]
    assert symbols == sorted(iparams._INSTRUMENT_PARAMS)  # sorted, exactly the single source
    assert all(isinstance(i, InstrumentInfo) for i in items)


def test_list_endpoint_200() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/instruments")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and body
    assert {b["symbol"] for b in body} == set(iparams._INSTRUMENT_PARAMS)
    assert all("balance" not in set(b.keys()) for b in body)  # no balance field


# ---- contract: frozen DTOs/ports + existing endpoints unchanged -----------------

def test_frozen_contracts_unchanged() -> None:
    assert set(InstrumentInfo.model_fields.keys()) == {
        "symbol", "tick_size", "min_qty", "max_qty", "fee_schedule_ref",
    }
    assert set(SymbolInfo.model_fields.keys()) == {
        "symbol", "base_asset", "quote_asset", "price_precision", "qty_precision", "status",
    }
    # ports remain their canonical Protocols (frozen surface)
    assert hasattr(MarketDataPort, "list_symbols")
    assert hasattr(FeeEnginePort, "compute")  # fee SoT untouched / not duplicated


def test_existing_instrument_endpoints_unchanged() -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/symbols").status_code == 200
    r = client.get("/api/v1/instruments/BTC-EUR")
    assert r.status_code == 200
    assert r.json() == instrument_info("BTC-EUR").model_dump(by_alias=True)
    assert client.get("/api/v1/instruments/DOGE-EUR").status_code == 404


# ---- negative / fail-closed ------------------------------------------------------

def test_list_skips_malformed_config(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    bad = {
        "BTC-EUR": dict(iparams._INSTRUMENT_PARAMS["BTC-EUR"]),  # valid
        "BAD-XXX": {"tick_size": "0.1"},                          # malformed (missing fields)
    }
    monkeypatch.setattr(iparams, "_INSTRUMENT_PARAMS", bad)
    items = list_instruments()
    assert [i.symbol for i in items] == ["BTC-EUR"]  # malformed skipped, no fabricated entry
