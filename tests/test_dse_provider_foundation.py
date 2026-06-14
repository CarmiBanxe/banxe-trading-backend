"""DSE provider foundation (Sprint S10) — tiers, fail-closed, mock-default.

No network, no credentials. Covers the tier matrix (MOCK / STUB / LIVE_READY),
deterministic provider outputs, fail-closed validation of unsafe combinations,
mock-default behaviour, safe (no-secret) provenance, and contract stability of
POST /v1/dss/recommend.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.dse import (
    LiveProviderNotWiredError,
    MockDseEngine,
    ProviderTier,
    foundation_profile,
    resolve_foundation,
)

_BODY = {"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced"}

# The stable top-level keys of the POST /v1/dss/recommend response (contract).
_RESPONSE_KEYS = {
    "recommendations", "sentiment", "modelVersions", "disclaimer",
    "analyticsContext", "traceId", "explanationVersion", "decisionTrace",
    "product", "asOf",
}


# ------------------------------ tier matrix --------------------------------- #


def test_tier_enum_values() -> None:
    assert {t.value for t in ProviderTier} == {"mock", "stub", "live-ready"}


def test_default_foundation_is_all_mock() -> None:
    f = resolve_foundation(Settings())
    assert (f.market_tier, f.sentiment_tier, f.stress_tier) == ("mock", "mock", "mock")
    prof = foundation_profile(f)
    assert prof["sentiment"]["source"] == "MockSentimentProvider"
    assert prof["market"]["source"] == "MockMarketDataProvider"


def test_stub_tier_returns_neutral_deterministic_values() -> None:
    f = resolve_foundation(Settings(dse_sentiment_tier="stub", dse_market_tier="stub"))
    assert asyncio.run(f.sentiment.get_sentiment("BTC")).score == "0"
    assert asyncio.run(f.market.get_market("BTC")).price == "0"
    assert foundation_profile(f)["sentiment"]["tier"] == "stub"


def test_live_ready_is_inert_without_master_switch() -> None:
    # live-ready is CI-safe and inert: no network, no creds, deterministic.
    f = resolve_foundation(Settings(dse_market_tier="live-ready"))
    snap = asyncio.run(f.market.get_market("BTC"))
    assert snap.source == "live-ready-inert"
    assert snap.price == "67251.00"  # mock-equivalent → no behaviour change
    assert foundation_profile(f)["market"]["source"] == "LiveReadyMarketDataProvider"


# --------------------------- fail-closed validation ------------------------- #


def test_unknown_tier_fails_closed() -> None:
    with pytest.raises(LiveProviderNotWiredError, match="unknown DSE provider tier"):
        resolve_foundation(Settings(dse_stress_tier="banana"))


def test_live_ready_with_switch_but_no_credentials_fails_closed() -> None:
    with pytest.raises(LiveProviderNotWiredError, match="credentials"):
        resolve_foundation(Settings(dse_market_tier="live-ready", dse_live_allowed=True))


def test_live_ready_with_switch_and_credentials_still_fails_closed_no_adapter() -> None:
    # Even with credentials present, no live network adapter is wired (ODR).
    with pytest.raises(LiveProviderNotWiredError, match="not wired"):
        resolve_foundation(
            Settings(
                dse_market_tier="live-ready",
                dse_live_allowed=True,
                dse_market_api_key="placeholder",
                dse_market_base_url="https://market.example",
            )
        )


def test_create_app_fails_closed_on_unsafe_combo() -> None:
    with pytest.raises(LiveProviderNotWiredError):
        create_app(Settings(dse_sentiment_tier="live-ready", dse_live_allowed=True))


def test_from_settings_resolves_foundation_fail_closed() -> None:
    with pytest.raises(LiveProviderNotWiredError):
        MockDseEngine.from_settings(Settings(dse_stress_tier="nope"))


# ------------------------- mock-default + provenance ------------------------ #


def test_app_starts_mock_and_remains_functional_without_live_env() -> None:
    # No live env vars → fully functional in mock mode.
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    health = client.get("/internal/health/dse-baas").json()
    assert health["status"] == "OK"
    assert health["checks"]["foundation"]["sentiment"]["tier"] == "mock"


def test_foundation_profile_carries_no_secrets() -> None:
    import json

    f = resolve_foundation(Settings(dse_market_tier="live-ready"))
    blob = json.dumps(foundation_profile(f)).lower()
    for forbidden in ("key", "secret", "token", "http://", "https://", "api_key"):
        assert forbidden not in blob


# ----------------------- contract stability of the endpoint ----------------- #


def test_recommend_contract_is_stable_under_foundation() -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    body = client.post("/v1/dss/recommend", json=_BODY).json()
    assert set(body.keys()) == _RESPONSE_KEYS  # no added/removed top-level fields
    ranks = [r["rank"] for r in body["recommendations"]]
    assert ranks == list(range(1, len(ranks) + 1))
    scores = [r["utilityScore"] for r in body["recommendations"]]
    assert scores == sorted(scores, key=float, reverse=True)


def test_ranking_unchanged_between_mock_and_inert_live_ready() -> None:
    # live-ready (inert) must not change utility/ranking vs mock.
    base = MockDseEngine.from_settings(Settings())
    lr = MockDseEngine.from_settings(
        Settings(dse_sentiment_tier="live-ready", dse_stress_tier="live-ready")
    )
    from banxe_trading_backend.dse import RecommendRequest

    req = RecommendRequest(asset="BTCUSDT", portfolio_value_usd="10000")
    a = asyncio.run(base.recommend(req))
    b = asyncio.run(lr.recommend(req))
    assert [r.utility_score for r in a.recommendations] == [
        r.utility_score for r in b.recommendations
    ]
    assert [r.action.type for r in a.recommendations] == [
        r.action.type for r in b.recommendations
    ]
