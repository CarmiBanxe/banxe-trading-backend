"""M1.8 — advisory crypto asset catalogue (additive, read-only, config-as-data, mock-safe).

characterization: catalogue assembly (reuses symbol asset universe) + endpoint 200; contract:
SymbolInfo/InstrumentInfo/MarketDataPort + /symbols, /instruments, earn, accounts endpoints
unchanged; negative: fail-closed (malformed market-data / config; never a fake value).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.assets.catalog import (
    AssetCatalogResponse,
    CryptoAssetMetadata,
    asset_catalog,
)
from banxe_trading_backend.dse.models import EarnMetrics
from banxe_trading_backend.models import InstrumentInfo, SymbolInfo
from banxe_trading_backend.ports.market_data_port import InMemoryMockMarketData

# ---- characterization ------------------------------------------------------------

def test_catalog_reuses_symbol_asset_universe() -> None:
    md = InMemoryMockMarketData()
    resp = asset_catalog(md)
    assert isinstance(resp, AssetCatalogResponse)
    assert resp.source == "sandbox-mock"
    assets = {a.asset for a in resp.assets}
    # universe must come from the symbol catalogue base/quote assets (e.g. BTC, ETH, EUR)
    universe: set[str] = set()
    for s in md.list_symbols():
        universe.update({s.base_asset, s.quote_asset})
    assert assets == universe
    for a in resp.assets:
        assert isinstance(a, CryptoAssetMetadata)
        assert a.asset_class in {"crypto", "stablecoin", "fiat"}
        assert isinstance(a.networks, list)
        assert isinstance(a.display_decimals, int)
        assert a.source == "sandbox-mock"


def test_catalog_deterministic_sorted_dedup() -> None:
    md = InMemoryMockMarketData()
    a1 = [a.asset for a in asset_catalog(md).assets]
    a2 = [a.asset for a in asset_catalog(md).assets]
    assert a1 == a2 == sorted(set(a1))  # deterministic, deduplicated, sorted


def test_catalog_endpoint_200() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/assets/metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["assets"]
    assert body["source"] == "sandbox-mock"
    keys = set(body["assets"][0].keys())
    assert not (keys & {"balance", "balances", "amount", "posting", "txn", "transactions"})


# ---- contract: frozen SoT + existing endpoints unchanged ------------------------

def test_symbol_contracts_frozen() -> None:
    assert set(SymbolInfo.model_fields.keys()) == {
        "symbol", "base_asset", "quote_asset", "price_precision", "qty_precision", "status",
    }
    assert set(InstrumentInfo.model_fields.keys()) == {
        "symbol", "tick_size", "min_qty", "max_qty", "fee_schedule_ref",
    }
    assert set(EarnMetrics.model_fields.keys()) == {
        "current_yield_pct", "protocol", "chain", "lockup_days", "variable_rate", "risk_summary",
    }


def test_existing_endpoints_unchanged() -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/symbols").status_code == 200
    assert client.get("/api/v1/instruments/BTC-EUR").status_code == 200
    assert client.get("/api/v1/earn/rates").status_code == 200
    assert client.get("/api/v1/accounts/metadata").status_code == 200


# ---- negative / fail-closed ------------------------------------------------------

class _BadMarketData:
    def list_symbols(self) -> list[SymbolInfo]:
        raise RuntimeError("market-data unavailable")


def test_fail_closed_on_unavailable_market_data() -> None:
    resp = asset_catalog(_BadMarketData())  # type: ignore[arg-type]
    assert resp.assets == []  # fail-closed: empty, no fabricated assets
    assert resp.source == "sandbox-mock"
