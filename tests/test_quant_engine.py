"""Quant-moat advisory seam (S14 / X9.3) — internal, mock-safe.

No network, no live models. Covers deterministic signal generation, the
volatility-regime classification, the fair-value/stress derivation, validation,
fail-closed non-mock provider, internal-only (not on /v1), and that CORE
contracts (DSE / mm / fees / execution-intent) are unchanged.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.ports import (
    MockQuantEngine,
    QuantPreviewRequest,
    build_quant_provider,
)

_URL = "/api/v1/quant/preview"


def _client() -> TestClient:
    return TestClient(create_app())


def _post(body: dict) -> dict:
    return _client().post(_URL, json=body).json()


# ------------------------------ engine signals ------------------------------ #


def _compute(**kw: object):
    return MockQuantEngine().compute(QuantPreviewRequest.model_validate(kw))


def test_eth_perp_signals_are_deterministic_and_consistent() -> None:
    out = _compute(asset="ETH", productType="perp", notionalUsd="2000", horizonDays=7)
    assert out.mode == "sandbox-mock"
    assert out.volatility_regime == "high"
    # fair value = 2000 × (1 + gap/10000); gap is regime-high magnitude (±75).
    assert abs(Decimal(out.fair_value_gap_bps)) == Decimal("75.00")
    expected_fv = (Decimal("2000") * (1 + Decimal(out.fair_value_gap_bps) / 10000)).quantize(
        Decimal("0.01")
    )
    assert Decimal(out.fair_value_usd) == expected_fv
    assert Decimal(out.stress_pnl_downside_pct) == Decimal("-15.00")  # high regime, 7d
    kinds = {s.kind for s in out.signals}
    assert {"fair_value_gap", "stress_scenario_score", "volatility_regime"} <= kinds
    assert "inventory_risk_flag" in kinds  # perp + high regime


def test_deterministic_for_same_input() -> None:
    a = _post({"asset": "ETH", "productType": "perp", "notionalUsd": "2000", "horizonDays": 7})
    b = _post({"asset": "ETH", "productType": "perp", "notionalUsd": "2000", "horizonDays": 7})
    assert a == b


def test_volatility_regime_classification() -> None:
    def regime(asset: str, pt: str) -> str:
        return _compute(asset=asset, productType=pt, notionalUsd="1000").volatility_regime or ""

    assert regime("USDC", "earn") == "low"
    assert regime("BTC", "perp") == "high"
    assert regime("SOL", "spot") == "medium"


def test_scores_are_bounded() -> None:
    out = _compute(asset="BTC", productType="perp", notionalUsd="5000", horizonDays=30)
    for s in out.signals:
        assert Decimal("-1") <= Decimal(s.score) <= Decimal("1")


def test_horizon_scales_stress() -> None:
    short = _compute(asset="ETH", productType="perp", notionalUsd="1000", horizonDays=7)
    long = _compute(asset="ETH", productType="perp", notionalUsd="1000", horizonDays=37)
    assert Decimal(long.stress_pnl_downside_pct) < Decimal(short.stress_pnl_downside_pct)


# ------------------------------ validation ---------------------------------- #


def test_validation_errors_are_422() -> None:
    client = _client()
    base = {"asset": "ETH", "productType": "perp", "notionalUsd": "1000", "horizonDays": 7}
    assert client.post(_URL, json={**base, "notionalUsd": "0"}).status_code == 422
    assert client.post(_URL, json={**base, "horizonDays": 0}).status_code == 422
    assert client.post(_URL, json={**base, "asset": ""}).status_code == 422
    assert client.post(_URL, json={**base, "productType": "swap"}).status_code == 422


# --------------------------- fail-closed / mock-only ------------------------ #


def test_non_mock_provider_is_operator_gated() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        build_quant_provider("remizov")


def test_create_app_fails_closed_on_non_mock_provider() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        create_app(Settings(quant_provider="heston"))


# ------------------- internal-only + core contracts intact ------------------ #


def test_not_on_external_v1_facade() -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    body = {"asset": "ETH", "productType": "perp", "notionalUsd": "1000", "horizonDays": 7}
    assert client.post("/v1/quant/preview", json=body).status_code == 404
    assert client.post(_URL, json=body).status_code == 200


def test_core_contracts_unchanged() -> None:
    client = _client()
    dss = client.post(
        "/api/v1/dss/recommend", json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"}
    )
    assert dss.status_code == 200
    recs = dss.json()["recommendations"]
    assert [r["rank"] for r in recs] == list(range(1, len(recs) + 1))
    fees_body = {"venue": "x", "productType": "spot", "asset": "ETH", "notionalUsd": "1000"}
    for url, payload in (
        ("/api/v1/mm/preview", {"asset": "BTCUSDT", "spreadBps": 10, "levels": 2}),
        ("/api/v1/fees/preview", fees_body),
        (
            "/api/v1/execution/intent-preview",
            {"asset": "BTCUSDT", "actionType": "BUY", "notionalUsd": "100"},
        ),
    ):
        assert client.post(url, json=payload).status_code == 200
