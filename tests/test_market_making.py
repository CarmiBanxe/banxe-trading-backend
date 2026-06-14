"""Market-making advisory seam (S12 / X9.1) — internal, mock/sandbox-only.

No network. Covers the deterministic symmetric ladder, unsigned/not-submitted
invariants, mid derivation via the (mock) ExchangePort, validation, fail-closed
non-mock provider, that it is NOT on the external /v1 facade, and that the DSE +
execution-intent contracts are unchanged.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.ports import MockMarketMakingStrategy, build_mm_provider

_URL = "/api/v1/mm/preview"


def _client() -> TestClient:
    return TestClient(create_app())


def _post(body: dict) -> dict:
    return _client().post(_URL, json=body).json()


# ------------------------------ strategy ladder ----------------------------- #


def test_ladder_is_symmetric_and_deterministic() -> None:
    rungs = MockMarketMakingStrategy().build_ladder(
        asset="BTCUSDT", mid=Decimal("100"), spread_bps=10, levels=2, size_usd=Decimal("500")
    )
    assert len(rungs) == 4  # 2 levels × (bid, ask)
    by = {(r.level, r.side): r for r in rungs}
    # level 1: 10 bps → 0.1 off 100 → bid 99.90 / ask 100.10
    assert by[(1, "buy")].price == "99.90" and by[(1, "sell")].price == "100.10"
    # level 2: 20 bps cumulative → bid 99.80 / ask 100.20
    assert by[(2, "buy")].price == "99.80" and by[(2, "sell")].price == "100.20"
    assert by[(2, "buy")].spread_bps == 20
    assert all(r.size_usd == "500" for r in rungs)


def test_preview_is_unsigned_and_not_submitted() -> None:
    body = _post({"asset": "BTCUSDT", "spreadBps": 10, "levels": 3, "sizeUsd": "1000"})
    assert body["mode"] == "sandbox-mock"
    assert body["signed"] is False and body["submitted"] is False
    assert len(body["rungs"]) == 6
    assert body["disclaimer"]
    # bids strictly below mid, asks strictly above.
    mid = Decimal(body["mid"])
    for r in body["rungs"]:
        if r["side"] == "buy":
            assert Decimal(r["price"]) < mid
        else:
            assert Decimal(r["price"]) > mid


def test_mid_derived_from_mock_rate_when_absent() -> None:
    # Mock ExchangePort bid 67250 / ask 67251 → mid 67250.50 (deterministic).
    body = _post({"asset": "BTCUSDT", "spreadBps": 10, "levels": 1})
    assert body["mid"] == "67250.50"


def test_mid_price_override_is_used() -> None:
    body = _post({"asset": "ETH-USDT", "midPrice": "3000", "spreadBps": 20, "levels": 1})
    prices = {r["side"]: r["price"] for r in body["rungs"]}
    assert prices == {"buy": "2994.00", "sell": "3006.00"}


# ------------------------------ validation ---------------------------------- #


def test_validation_errors_are_422() -> None:
    client = _client()
    assert client.post(_URL, json={"asset": "BTCUSDT", "spreadBps": 0}).status_code == 422
    assert client.post(_URL, json={"asset": "BTCUSDT", "levels": 0}).status_code == 422
    assert client.post(_URL, json={"asset": "BTCUSDT", "levels": 99}).status_code == 422
    assert client.post(_URL, json={"asset": "BTCUSDT", "sizeUsd": "0"}).status_code == 422
    assert client.post(_URL, json={"asset": "BTCUSDT", "midPrice": "0"}).status_code == 422


# --------------------------- fail-closed / mock-only ------------------------ #


def test_non_mock_provider_is_operator_gated() -> None:
    import pytest

    with pytest.raises(ValueError, match="operator-gated"):
        build_mm_provider("hummingbot")


def test_create_app_fails_closed_on_non_mock_provider() -> None:
    import pytest

    with pytest.raises(ValueError, match="operator-gated"):
        create_app(Settings(mm_provider="hummingbot"))


# ------------------- internal-only + core contracts intact ------------------ #


def test_not_on_external_v1_facade() -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    assert client.post("/v1/mm/preview", json={"asset": "BTCUSDT"}).status_code == 404
    assert client.post(_URL, json={"asset": "BTCUSDT"}).status_code == 200


def test_core_contracts_unchanged() -> None:
    client = _client()
    dss = client.post(
        "/api/v1/dss/recommend", json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"}
    )
    assert dss.status_code == 200
    ranks = [r["rank"] for r in dss.json()["recommendations"]]
    assert ranks == list(range(1, len(ranks) + 1))
    intent = client.post(
        "/api/v1/execution/intent-preview",
        json={"asset": "BTCUSDT", "actionType": "BUY", "notionalUsd": "100"},
    )
    assert intent.status_code == 200 and intent.json()["submitted"] is False
