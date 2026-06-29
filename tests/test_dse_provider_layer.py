"""DSE provider-layer & live-provider safety-rails (T8.3) — mock-default.

No network. Verifies the provider-mode enum + config seams, the startup
safety-rail that refuses any non-mock (ODR) configuration, the safe (no-secret)
provider profile, the observability providerMode wiring, and that default
behaviour (utility/ranking) is unchanged.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.dse import (
    LiveProviderNotWiredError,
    ProviderMode,
    assert_mock_only,
    provider_profile,
)

_BODY = {"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced"}


# ------------------------------ mode + config ------------------------------- #


def test_provider_mode_enum_values() -> None:
    assert ProviderMode.MOCK.value == "mock"
    assert {m.value for m in ProviderMode} == {"mock", "sandbox-live", "prod-live"}


def test_config_defaults_are_all_mock_and_keys_empty() -> None:
    s = Settings()
    assert s.dse_provider_mode == "mock"
    assert s.dse_market_provider == "mock"
    # Future live key/endpoint seams exist but are EMPTY (no real values).
    for field in (
        "dse_market_api_key", "dse_market_base_url",
        "dse_sentiment_api_key", "dse_sentiment_base_url",
        "dse_stress_api_key", "dse_stress_base_url",
        "dse_earn_api_key", "dse_earn_base_url",
    ):
        assert getattr(s, field) == ""


# ------------------------------- safety-rail -------------------------------- #


def test_assert_mock_only_passes_for_defaults() -> None:
    assert_mock_only(Settings())  # no raise


def test_non_mock_mode_is_operator_gated() -> None:
    # prod-live remains ODR-gated (no live wiring). sandbox-live is allowed now
    # (S6.2-EN) but kill-switch off / partial combo silently fall back to mock.
    with pytest.raises(LiveProviderNotWiredError, match="OPERATOR-GATED"):
        assert_mock_only(Settings(dse_provider_mode="prod-live"))


def test_sandbox_live_kill_switch_off_does_not_raise() -> None:
    # S6.2-EN: sandbox-live mode without the full dydx + kill-switch combo must
    # fail-closed (i.e. NOT raise) — the runtime simply mocks the market route.
    assert_mock_only(Settings(dse_provider_mode="sandbox-live"))


def test_sandbox_live_full_dydx_combo_passes() -> None:
    # The one wired sandbox-live route: all three flags ON, all other domains mock.
    assert_mock_only(Settings(
        dse_provider_mode="sandbox-live",
        dse_market_provider="dydx",
        dse_live_allowed=True,
    ))


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(LiveProviderNotWiredError, match="unknown DSE provider mode"):
        assert_mock_only(Settings(dse_provider_mode="banana"))


@pytest.mark.parametrize(
    "field",
    ["dse_market_provider", "dse_sentiment_provider", "dse_stress_provider",
     "dse_risk_provider", "dse_earn_provider", "risk_greeks_provider", "earn_rates_provider"],
)
def test_non_mock_provider_value_is_operator_gated(field: str) -> None:
    with pytest.raises(LiveProviderNotWiredError, match="not wired"):
        assert_mock_only(Settings(**{field: "live"}))


def test_create_app_refuses_prod_live_config() -> None:
    # prod-live mode is OPERATOR-GATED — no live wiring exists this sprint.
    with pytest.raises(LiveProviderNotWiredError):
        create_app(Settings(dse_provider_mode="prod-live"))


def test_create_app_refuses_unwired_live_provider() -> None:
    # An unwired live value on any domain still raises (only market=dydx is wired).
    with pytest.raises(LiveProviderNotWiredError):
        create_app(Settings(dse_sentiment_provider="live"))


# ------------------------------- safe profile ------------------------------- #


def test_provider_profile_is_all_mock_no_secrets() -> None:
    profile = provider_profile(Settings())
    assert profile.mode == "mock"
    d = profile.to_dict()
    assert d == {"mode": "mock", "market": "mock", "sentiment": "mock",
                 "stress": "mock", "earn": "mock"}
    # The profile must never carry keys/endpoints.
    blob = json.dumps(d).lower()
    for forbidden in ("key", "secret", "token", "http://", "https://"):
        assert forbidden not in blob


# ----------------------- observability: providerMode ------------------------ #


def test_metrics_expose_provider_mode() -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    client.post("/v1/dss/recommend", json=_BODY)
    text = client.get("/internal/metrics/dse-baas").text
    assert 'dse_baas_requests_by_mode_total{provider_mode="mock"} 1' in text


def test_health_reports_provider_mode() -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    assert client.get("/internal/health/dse-baas").json()["checks"]["providerMode"] == "mock"


def test_structured_log_carries_provider_mode(caplog) -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    with caplog.at_level(logging.INFO, logger="banxe.dse.baas"):
        client.post("/v1/dss/recommend", json=_BODY)
    event = json.loads(next(r.getMessage() for r in caplog.records if r.name == "banxe.dse.baas"))
    assert event["providerMode"] == "mock"
    assert event["providerProfile"]["sentiment"] == "mock"
    # Still no secrets/endpoints in the log.
    blob = json.dumps(event).lower()
    for forbidden in ("api_key", "secret", "http://", "https://"):
        assert forbidden not in blob


# ------------------------- behaviour unchanged ------------------------------ #


def test_default_behaviour_unchanged() -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    body = client.post("/v1/dss/recommend", json=_BODY).json()
    # Ranking/utility still the established mock output (provider-layer is wiring).
    ranks = [r["rank"] for r in body["recommendations"]]
    assert ranks == list(range(1, len(ranks) + 1))
    scores = [r["utilityScore"] for r in body["recommendations"]]
    assert scores == sorted(scores, key=float, reverse=True)
