"""Read-only Risk/Earn BaaS sandbox endpoints (T7.5).

No network: deterministic mock providers only. Covers query parsing, full mock
payloads with the `source: "sandbox-mock"` flag, operator-gated non-mock
providers, and OpenAPI spec ↔ pydantic model conformance.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.earn import (
    EarnRatesResponse,
    RateCard,
    build_earn_rates_catalog,
)
from banxe_trading_backend.earn.providers import MockEarnRatesProvider
from banxe_trading_backend.risk import (
    PortfolioGreeksResponse,
    build_risk_greeks_provider,
)
from banxe_trading_backend.risk.greeks import Greeks

_SPECS = Path(__file__).resolve().parents[1] / "docs" / "specs"


# --------------------------- GET /v1/risk/greeks ---------------------------- #


def test_greeks_endpoint_returns_sandbox_mock_payload() -> None:
    client = TestClient(create_app())
    resp = client.get(
        "/api/v1/risk/greeks",
        params={"asset": "BTCUSDT", "portfolioValueUsd": "10000", "positionUsd": "5000"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["asset"] == "BTCUSDT"
    assert body["source"] == "sandbox-mock"
    assert body["disclaimer"]  # MiCA/MiFID advisory disclosure present
    assert set(body["greeks"]) == {"delta", "gamma", "vega", "theta", "rho"}
    # long 5000 / 10000 portfolio → delta 0.5 (deterministic mock).
    assert Decimal(body["greeks"]["delta"]) == Decimal("0.5000")
    assert body["notionalUsd"] == "5000.00"


def test_greeks_short_side_flips_delta_sign() -> None:
    client = TestClient(create_app())
    resp = client.get(
        "/api/v1/risk/greeks",
        params={
            "asset": "ETHUSDT",
            "portfolioValueUsd": "10000",
            "positionUsd": "5000",
            "side": "short",
        },
    )
    assert resp.status_code == 200
    assert Decimal(resp.json()["greeks"]["delta"]) == Decimal("-0.5000")


def test_greeks_rejects_bad_decimal_and_bad_side() -> None:
    client = TestClient(create_app())
    bad_dec = client.get("/api/v1/risk/greeks", params={"asset": "BTC", "positionUsd": "abc"})
    assert bad_dec.status_code == 422
    bad_side = client.get("/api/v1/risk/greeks", params={"asset": "BTC", "side": "sideways"})
    assert bad_side.status_code == 422


# ---------------------------- GET /v1/earn/rates ---------------------------- #


def test_earn_rates_default_basket_sandbox_mock() -> None:
    client = TestClient(create_app())
    resp = client.get("/api/v1/earn/rates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "sandbox-mock"
    assert body["disclaimer"]
    assets = [c["asset"] for c in body["rates"]]
    assert assets == ["BTC", "ETH", "USDC"]  # default basket
    for card in body["rates"]:
        assert set(card) == {
            "asset", "protocol", "apyPct", "lockupDays",
            "variableRate", "riskBand", "source",
        }
        assert card["source"] == "sandbox-mock"
        assert card["riskBand"] in {"low", "medium", "high"}
    usdc = next(c for c in body["rates"] if c["asset"] == "USDC")
    assert usdc["riskBand"] == "low"
    assert Decimal(usdc["apyPct"]) == Decimal("5.0000")


def test_earn_rates_explicit_assets() -> None:
    client = TestClient(create_app())
    resp = client.get("/api/v1/earn/rates", params=[("assets", "ETH"), ("assets", "SOL")])
    assert resp.status_code == 200
    cards = resp.json()["rates"]
    assert [c["asset"] for c in cards] == ["ETH", "SOL"]
    # Unknown asset → generic mock + HIGH band (no network lookup).
    sol = cards[1]
    assert sol["protocol"] == "mock-generic"
    assert sol["riskBand"] == "high"


# ----------------------- providers are mock-only / no network --------------- #


def test_risk_greeks_provider_non_mock_is_operator_gated() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        build_risk_greeks_provider("stakekit")


def test_earn_rates_catalog_non_mock_is_operator_gated() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        build_earn_rates_catalog("aave", MockEarnRatesProvider())


# ----------------------- OpenAPI spec ↔ model conformance ------------------- #


def _schema_props(spec_file: str, schema: str) -> set[str]:
    doc = yaml.safe_load((_SPECS / spec_file).read_text())
    return set(doc["components"]["schemas"][schema]["properties"].keys())


def _aliases(model: type) -> set[str]:
    return {fi.alias or name for name, fi in model.model_fields.items()}  # type: ignore[attr-defined]


def test_models_match_risk_earn_specs() -> None:
    cases = [
        (Greeks, "risk-api.yaml", "Greeks"),
        (PortfolioGreeksResponse, "risk-api.yaml", "PortfolioGreeksResponse"),
        (RateCard, "earn-api.yaml", "RateCard"),
        (EarnRatesResponse, "earn-api.yaml", "EarnRatesResponse"),
    ]
    for model, spec_file, schema in cases:
        assert _aliases(model) == _schema_props(spec_file, schema), f"{schema} mismatch"
