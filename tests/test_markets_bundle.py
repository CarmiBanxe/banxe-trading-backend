"""M1.12 — markets advisory bundle (instrument<->asset xref list, read-only, mock-safe).

characterization: deterministic bundle over the M1.11 single xref + endpoint 200; contract:
frozen DTOs + existing endpoints unchanged; negative: fail-closed (unresolvable entry skipped).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.assets.catalog import CryptoAssetMetadata
from banxe_trading_backend.instruments import params as iparams
from banxe_trading_backend.instruments import xref as ixref
from banxe_trading_backend.instruments.xref import (
    InstrumentAssetXref,
    instrument_asset_xref,
    list_instrument_asset_xref,
)
from banxe_trading_backend.models import InstrumentInfo, SymbolInfo


def test_bundle_deterministic_over_single_xref() -> None:
    bundle = list_instrument_asset_xref()
    assert bundle == list_instrument_asset_xref()  # deterministic
    symbols = [b.symbol for b in bundle]
    assert symbols == sorted(iparams._INSTRUMENT_PARAMS)  # sorted, exactly the catalogue
    assert all(isinstance(b, InstrumentAssetXref) for b in bundle)
    # each entry equals the M1.11 single xref (reuse, not a second source)
    assert bundle[0] == instrument_asset_xref(bundle[0].symbol)


def test_markets_endpoint_200() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/markets")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and body
    assert {b["symbol"] for b in body} == set(iparams._INSTRUMENT_PARAMS)
    first = body[0]
    assert first["baseAsset"]["asset"] and first["quoteAsset"]["asset"]
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
        "/api/v1/instruments/BTC-EUR/assets", "/api/v1/assets/metadata",
    ):
        assert client.get(p).status_code == 200


def test_bundle_fail_closed_skips_unresolvable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # inject an extra symbol whose params exist but whose xref assembly raises -> skipped, no fake
    good = dict(iparams._INSTRUMENT_PARAMS)

    def boom(symbol: str) -> InstrumentAssetXref:
        if symbol == "BAD-XXX":
            raise RuntimeError("unresolvable market")
        return instrument_asset_xref(symbol)

    monkeypatch.setattr(ixref, "list_instruments", lambda: [
        InstrumentInfo(
            symbol=s, tick_size="0.01", min_qty="0.1", max_qty="1", fee_schedule_ref="r",
        )
        for s in [*sorted(good), "BAD-XXX"]
    ])
    monkeypatch.setattr(ixref, "instrument_asset_xref", boom)
    bundle = list_instrument_asset_xref()
    assert "BAD-XXX" not in [b.symbol for b in bundle]
    assert len(bundle) == len(good)
