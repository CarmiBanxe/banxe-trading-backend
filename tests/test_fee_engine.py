"""Dynamic fee engine — advisory seam (S13 / X9.2), internal, mock-safe.

No network, no billing. Covers the fee decomposition (bps/usd, tier discount,
negative maker rebate, per-product schemes), the totals, validation, fail-closed
non-mock provider, internal-only (not on /v1), and that CORE contracts (DSE +
market-making + execution-intent) are unchanged.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.ports import (
    FeePreviewRequest,
    MockFeeEngine,
    build_fee_provider,
)

_URL = "/api/v1/fees/preview"


def _client() -> TestClient:
    return TestClient(create_app())


def _post(body: dict) -> dict:
    return _client().post(_URL, json=body).json()


# ------------------------------ engine math --------------------------------- #


def _components(**kw: object) -> dict[str, Decimal]:
    req = FeePreviewRequest.model_validate(kw)
    return {c.kind: Decimal(c.bps) for c in MockFeeEngine().compute(req)}


def test_spot_with_tier_rebate_and_referral() -> None:
    comps = _components(
        venue="dydx-v4", productType="spot", asset="ETH", notionalUsd="1000",
        partnerTier="PRO", makerRebateEligible=True, referralCode="GMX-REF-001",
    )
    # integrator 25 × 0.8 = 20; referral 10 × 0.8 = 8; rebate -3; spread 8.
    assert comps == {
        "integrator_fee": Decimal("20.00"),
        "referral_fee": Decimal("8.00"),
        "maker_rebate": Decimal("-3.00"),
        "bid_ask_spread_capture": Decimal("8.00"),
    }


def test_perp_and_earn_schemes() -> None:
    perp = _components(venue="dydx", productType="perp", asset="BTC", notionalUsd="5000")
    assert perp == {"builder_code_fee": Decimal("5.00"), "bid_ask_spread_capture": Decimal("5.00")}
    earn = _components(venue="stakekit", productType="earn", asset="USDC", notionalUsd="10000")
    assert earn == {"performance_fee": Decimal("200.00")}


def test_zero_bps_components_are_omitted() -> None:
    # No tier/rebate/referral on spot → integrator + spread only (builder/perf=0).
    comps = _components(venue="x", productType="spot", asset="ETH", notionalUsd="1000")
    assert set(comps) == {"integrator_fee", "bid_ask_spread_capture"}


# ------------------------------ endpoint totals ----------------------------- #


def test_endpoint_totals_and_envelope() -> None:
    body = _post({
        "venue": "dydx-v4", "route": "lifi-spot", "productType": "spot", "asset": "ETH",
        "notionalUsd": "1000", "partnerTier": "PRO", "makerRebateEligible": True,
        "referralCode": "GMX-REF-001",
    })
    assert body["mode"] == "sandbox-mock"
    assert body["signed"] is False and body["submitted"] is False
    # totals = 20 + 8 - 3 + 8 = 33 bps → 1000 × 33/10000 = 3.30 usd.
    assert body["totalFeeBps"] == "33.00"
    assert Decimal(body["totalFeeUsd"]) == Decimal("3.3000")
    assert sum(Decimal(c["usd"]) for c in body["components"]) == Decimal(body["totalFeeUsd"])
    assert body["disclaimer"]


# ------------------------------ validation ---------------------------------- #


def test_validation_errors_are_422() -> None:
    client = _client()
    base = {"venue": "x", "productType": "spot", "asset": "ETH", "notionalUsd": "1000"}
    assert client.post(_URL, json={**base, "notionalUsd": "0"}).status_code == 422
    assert client.post(_URL, json={**base, "notionalUsd": "-5"}).status_code == 422
    assert client.post(_URL, json={**base, "asset": ""}).status_code == 422
    assert client.post(_URL, json={**base, "productType": "options"}).status_code == 422


# --------------------------- fail-closed / mock-only ------------------------ #


def test_non_mock_provider_is_operator_gated() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        build_fee_provider("lago")


def test_create_app_fails_closed_on_non_mock_provider() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        create_app(Settings(fee_provider="stripe"))


# ------------------- internal-only + core contracts intact ------------------ #


def test_not_on_external_v1_facade() -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    body = {"venue": "x", "productType": "spot", "asset": "ETH", "notionalUsd": "1000"}
    assert client.post("/v1/fees/preview", json=body).status_code == 404
    assert client.post(_URL, json=body).status_code == 200


def test_core_contracts_unchanged() -> None:
    client = _client()
    dss = client.post(
        "/api/v1/dss/recommend", json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"}
    )
    assert dss.status_code == 200
    assert [r["rank"] for r in dss.json()["recommendations"]] == list(
        range(1, len(dss.json()["recommendations"]) + 1)
    )
    mm = client.post(
        "/api/v1/mm/preview", json={"asset": "BTCUSDT", "spreadBps": 10, "levels": 2}
    )
    assert mm.status_code == 200 and mm.json()["submitted"] is False
    intent = client.post(
        "/api/v1/execution/intent-preview",
        json={"asset": "BTCUSDT", "actionType": "BUY", "notionalUsd": "100"},
    )
    assert intent.status_code == 200 and intent.json()["submitted"] is False
