"""DSE (Decision Support Engine) — advisory-only, deterministic mock (T7.1).

No network. Covers utility per profile, Kelly/Half-Kelly, ranking, mock
sentiment/stress fixtures, OpenAPI spec ↔ pydantic conformance, and the
internal POST /api/v1/dss/recommend endpoint.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.dse import (
    AGGRESSIVE,
    BALANCED,
    CONSERVATIVE,
    Action,
    DseEngine,
    MockDseEngine,
    ModelVersions,
    Position,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
    RiskProfile,
    SentimentScore,
    StressScenario,
    StressTests,
    UtilityWeights,
)
from banxe_trading_backend.dse.kelly import half_kelly_fraction, kelly_fraction
from banxe_trading_backend.dse.utility import RiskMetrics, utility_score

_SPECS = Path(__file__).resolve().parents[1] / "docs" / "specs"
OPEN_LONG_METRICS = RiskMetrics(
    Decimal("0.08"), Decimal("0.04"), Decimal("0.06"), Decimal("0.05"), Decimal("0.90")
)


# --------------------------- utility per profile ---------------------------- #


def test_utility_monotonic_across_profiles() -> None:
    aggressive = utility_score(OPEN_LONG_METRICS, AGGRESSIVE)
    balanced = utility_score(OPEN_LONG_METRICS, BALANCED)
    conservative = utility_score(OPEN_LONG_METRICS, CONSERVATIVE)
    # A return-heavy action scores higher as the profile gets more aggressive.
    assert aggressive > balanced > conservative


def test_custom_weights_used_when_profile_custom() -> None:
    from banxe_trading_backend.dse import weights_for

    custom = UtilityWeights(
        w1_expected_return="3",
        w2_volatility="0",
        w3_var99="0",
        w4_drawdown="0",
        w5_liquidity="0",
    )
    w = weights_for(RiskProfile.CUSTOM, custom)
    assert w is custom
    # U = 3 * ER = 3 * 0.08 = 0.24
    assert utility_score(OPEN_LONG_METRICS, w) == Decimal("0.24")


# --------------------------- Kelly / Half-Kelly ----------------------------- #


def test_kelly_and_half_kelly() -> None:
    # p=0.55, b=1.5 → f* = (0.55*2.5 - 1)/1.5 = 0.25
    assert kelly_fraction(Decimal("0.55"), Decimal("1.5")) == Decimal("0.25")
    assert half_kelly_fraction(Decimal("0.55"), Decimal("1.5")) == Decimal("0.125")
    # Half is exactly half of full (the hard-limit default).
    full = kelly_fraction(Decimal("0.6"), Decimal("2"))
    assert half_kelly_fraction(Decimal("0.6"), Decimal("2")) == full / 2


def test_kelly_clamps_negative_edge_to_zero() -> None:
    # p=0.4, b=1 → negative edge → 0 (never negative sizing)
    assert kelly_fraction(Decimal("0.4"), Decimal("1")) == Decimal("0")
    assert kelly_fraction(Decimal("0.5"), Decimal("0")) == Decimal("0")  # no payoff


# --------------------------- ranking / engine ------------------------------- #


def _recommend(**kw: object) -> RecommendResponse:
    req = RecommendRequest(asset="BTCUSDT", portfolio_value_usd="10000", **kw)  # type: ignore[arg-type]
    return asyncio.run(MockDseEngine().recommend(req))


def test_engine_satisfies_protocol() -> None:
    assert isinstance(MockDseEngine(), DseEngine)


def test_recommendations_sorted_desc_and_ranked() -> None:
    resp = _recommend()
    scores = [Decimal(r.utility_score) for r in resp.recommendations]
    assert scores == sorted(scores, reverse=True)  # non-increasing
    assert [r.rank for r in resp.recommendations] == list(range(1, len(scores) + 1))
    # Every monetary/metric field is a decimal string (I-01).
    for r in resp.recommendations:
        Decimal(r.expected_return_pct)
        Decimal(r.kelly_size_pct)
        Decimal(r.half_kelly_size_pct)
        Decimal(r.utility_score)


def test_aggressive_ranks_buy_above_open_long() -> None:
    resp = _recommend(risk_profile=RiskProfile.AGGRESSIVE)
    ranks = {r.action.type.value: r.rank for r in resp.recommendations}
    assert ranks["BUY"] < ranks["OPEN_LONG"]


def test_sentiment_and_stress_are_deterministic_fixtures() -> None:
    a = _recommend()
    b = _recommend()
    assert a.sentiment == b.sentiment
    assert a.recommendations[0].stress_tests == b.recommendations[0].stress_tests
    assert a.sentiment.score == "0.35"
    top = a.recommendations[0]
    assert top.stress_tests is not None
    assert {
        top.stress_tests.base.name,
        top.stress_tests.shock_down.name,
        top.stress_tests.black_swan.name,
    } == {"base", "shockDown", "blackSwan"}


def test_include_flags_toggle_overlays() -> None:
    resp = _recommend(include_sentiment=False, include_stress_tests=False)
    assert all(r.sentiment is None for r in resp.recommendations)
    assert all(r.stress_tests is None for r in resp.recommendations)
    # Top-level sentiment is always present on the response.
    assert resp.sentiment is not None


# --------------------------- OpenAPI spec conformance ----------------------- #


def _schema_props(spec_file: str, schema: str) -> set[str]:
    doc = yaml.safe_load((_SPECS / spec_file).read_text())
    return set(doc["components"]["schemas"][schema]["properties"].keys())


def _aliases(model: type) -> set[str]:
    return {fi.alias or name for name, fi in model.model_fields.items()}  # type: ignore[attr-defined]


def test_models_match_openapi_specs() -> None:
    utility = "dse-utility-api.yaml"
    baas = "dse-baas-api.yaml"
    cases = [
        (UtilityWeights, utility, "UtilityWeights"),
        (Action, utility, "Action"),
        (SentimentScore, utility, "SentimentScore"),
        (StressScenario, utility, "StressScenario"),
        (StressTests, utility, "StressTests"),
        (Position, baas, "Position"),
        (Recommendation, baas, "Recommendation"),
        (ModelVersions, baas, "ModelVersions"),
        (RecommendRequest, baas, "RecommendRequest"),
        (RecommendResponse, baas, "RecommendResponse"),
    ]
    for model, spec_file, schema in cases:
        assert _aliases(model) == _schema_props(spec_file, schema), f"{schema} mismatch"


# --------------------------- API endpoint ----------------------------------- #


def test_recommend_endpoint_returns_ranked_advisory() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/dss/recommend",
        json={"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["disclaimer"]  # MiCA/MiFID advisory disclosure present
    assert set(body["modelVersions"]) == {"pricing", "sentiment", "kelly", "stress"}
    recs = body["recommendations"]
    assert [r["rank"] for r in recs] == list(range(1, len(recs) + 1))
    scores = [Decimal(r["utilityScore"]) for r in recs]
    assert scores == sorted(scores, reverse=True)
    assert recs[0]["action"]["asset"] == "BTCUSDT"


def test_custom_profile_without_weights_is_422() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/dss/recommend",
        json={"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "custom"},
    )
    assert resp.status_code == 422
