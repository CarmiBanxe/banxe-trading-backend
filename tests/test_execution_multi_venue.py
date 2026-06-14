"""Multi-venue unsigned execution-preview hardening (S16) — internal, mock-safe.

No network. Covers the additive multi-venue path (candidates + bestCandidate),
per-product default venues, deterministic ranking, the unsigned/not-submitted
invariants (top-level + per candidate), validation + fail-closed (config guard,
submit/sign/live flags, executionMode), and backward-compat of the T9.1
single-venue preview.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.services.intent_preview import build_execution_preview_provider

_URL = "/api/v1/execution/intent-preview"


def _client() -> TestClient:
    return TestClient(create_app())


def _post(body: dict) -> dict:
    return _client().post(_URL, json=body).json()


# ----------------------- backward compatibility (T9.1) ---------------------- #


def test_single_venue_preview_unchanged() -> None:
    body = _post({"asset": "BTCUSDT", "actionType": "OPEN_LONG", "notionalUsd": "10000"})
    assert body["tradable"] is True
    assert body["signed"] is False and body["submitted"] is False
    assert body["order"]["side"] == "buy"
    assert body["candidates"] is None and body["bestCandidate"] is None  # legacy shape


def test_single_venue_advisory_only_action_not_tradable() -> None:
    body = _post({"asset": "BTCUSDT", "actionType": "HOLD", "notionalUsd": "100"})
    assert body["tradable"] is False and body["order"] is None


# --------------------------- multi-venue breadth ---------------------------- #


def test_multi_venue_spot_returns_ranked_candidates() -> None:
    body = _post({
        "intentType": "swap", "asset": "ETH", "quoteAsset": "USDC", "notionalUsd": "1000",
        "venues": ["lifi", "0x"], "productType": "spot", "riskProfile": "balanced",
    })
    assert body["mode"] == "sandbox-mock"
    assert body["signed"] is False and body["submitted"] is False
    assert body["intentType"] == "swap" and body["productType"] == "spot"
    assert len(body["candidates"]) == 2
    # lifi (8 bps fee / 18 slip) beats 0x (12 / 22) → best lifi.
    assert body["bestCandidate"]["venue"] == "lifi"
    for c in body["candidates"]:
        assert c["signed"] is False and c["submitted"] is False
        assert {"venue", "route", "productType", "expectedPrice", "estimatedFeeUsd",
                "estimatedSlippageBps", "etaSeconds", "confidence"} <= set(c)


def test_default_venues_per_product() -> None:
    perp = _post({"asset": "ETH", "notionalUsd": "2000", "productType": "perp"})
    assert [c["venue"] for c in perp["candidates"]] == ["dydx-v4", "gmx-v2", "injective"]
    assert perp["bestCandidate"]["venue"] == "dydx-v4"
    earn = _post({"asset": "USDC", "notionalUsd": "5000", "productType": "earn"})
    assert [c["venue"] for c in earn["candidates"]] == ["stakekit", "aave-v3", "lido"]


def test_unknown_venue_uses_mock_defaults_with_note() -> None:
    body = _post(
        {"asset": "ETH", "notionalUsd": "1000", "productType": "spot", "venues": ["weirddex"]}
    )
    cand = body["candidates"][0]
    assert cand["venue"] == "weirddex" and cand["notes"]


def test_multi_venue_is_deterministic() -> None:
    payload = {"asset": "ETH", "notionalUsd": "1000", "productType": "perp"}
    assert _post(payload) == _post(payload)


# --------------------------- validation / fail-closed ----------------------- #


def test_validation_errors_are_422() -> None:
    client = _client()

    def status(body: dict) -> int:
        return client.post(_URL, json=body).status_code

    assert status({"asset": "ETH", "notionalUsd": "0", "productType": "spot"}) == 422
    assert status({"asset": "", "notionalUsd": "1", "productType": "spot"}) == 422
    assert status(
        {"asset": "ETH", "notionalUsd": "1", "productType": "spot", "venues": ["lifi", ""]}
    ) == 422
    assert status({"asset": "ETH", "notionalUsd": "1", "productType": "options"}) == 422
    assert status({"asset": "ETH", "notionalUsd": "1", "intentType": "nope"}) == 422
    assert status(
        {"asset": "ETH", "notionalUsd": "1", "productType": "spot", "executionMode": "live"}
    ) == 422


def test_submit_sign_live_flags_fail_closed() -> None:
    client = _client()
    base = {"asset": "ETH", "notionalUsd": "1", "productType": "spot"}
    for flag in ("submit", "sign", "live"):
        assert client.post(_URL, json={**base, flag: True}).status_code == 422  # extra=forbid


def test_non_mock_provider_is_operator_gated() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        build_execution_preview_provider("zerox-live")


def test_create_app_fails_closed_on_non_mock_provider() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        create_app(Settings(execution_preview_provider="live-submit"))


# ------------------- internal-only + core contracts intact ------------------ #


def test_not_on_external_v1_facade() -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    body = {"asset": "ETH", "notionalUsd": "1000", "productType": "spot"}
    assert client.post("/v1/execution/intent-preview", json=body).status_code == 404
    assert client.post(_URL, json=body).status_code == 200


def test_core_contracts_unchanged() -> None:
    client = _client()
    dss = client.post(
        "/api/v1/dss/recommend", json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"}
    )
    assert dss.status_code == 200
    fees_body = {"venue": "x", "productType": "spot", "asset": "ETH", "notionalUsd": "1000"}
    quant_body = {"asset": "ETH", "productType": "perp", "notionalUsd": "1000", "horizonDays": 7}
    for url, payload in (
        ("/api/v1/mm/preview", {"asset": "BTCUSDT", "spreadBps": 10, "levels": 2}),
        ("/api/v1/fees/preview", fees_body),
        ("/api/v1/quant/preview", quant_body),
    ):
        assert client.post(url, json=payload).status_code == 200
    assert client.get("/api/v1/marketplace/providers").status_code == 200
