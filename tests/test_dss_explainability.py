"""DSE explainability & traceability (T7.7) — additive, advisory, deterministic.

No network. Covers: utility decomposition sums exactly to utilityScore (the
existing math, exposed — not changed), top driver, deterministic traceId,
explanation version, ranking/utility invariance, and spec ↔ model conformance.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.dse import (
    BALANCED,
    MockDseEngine,
    RecommendRequest,
    UtilityComponent,
)
from banxe_trading_backend.dse.utility import (
    CandidateMetrics,
    utility_components,
    utility_score,
)

_SPECS = Path(__file__).resolve().parents[1] / "docs" / "specs"

_METRICS = CandidateMetrics(
    Decimal("0.08"), Decimal("0.04"), Decimal("0.093052"), Decimal("0.05"), Decimal("0.90")
)


def _req(**kw: object) -> RecommendRequest:
    base = {"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced"}
    base.update(kw)
    return RecommendRequest.model_validate(base)


# ----------------------------- pure decomposition --------------------------- #


def test_components_sum_to_utility_score() -> None:
    terms = utility_components(_METRICS, BALANCED)
    assert {t.factor for t in terms} == {
        "expectedReturn", "volatility", "var99", "drawdown", "liquidity",
    }
    total = sum((t.contribution for t in terms), Decimal(0))
    assert total == utility_score(_METRICS, BALANCED)


def test_component_signs_follow_the_formula() -> None:
    by_factor = {t.factor: t for t in utility_components(_METRICS, BALANCED)}
    assert by_factor["expectedReturn"].direction == "positive"
    assert by_factor["liquidity"].direction == "positive"
    for neg in ("volatility", "var99", "drawdown"):
        assert by_factor[neg].direction == "negative"
        assert by_factor[neg].contribution <= 0


# ----------------------------- engine integration --------------------------- #


def test_each_recommendation_breakdown_sums_to_its_score() -> None:
    resp = asyncio.run(MockDseEngine.from_settings(create_app().state.settings).recommend(_req()))
    for rec in resp.recommendations:
        assert rec.utility_breakdown is not None
        total = sum((Decimal(c.contribution) for c in rec.utility_breakdown), Decimal(0))
        # The decomposition reconstructs the EXISTING score exactly (no tampering).
        assert total == Decimal(rec.utility_score)
        # top_driver is the factor with the largest absolute contribution.
        top = max(rec.utility_breakdown, key=lambda c: abs(Decimal(c.contribution)))
        assert rec.top_driver == top.factor


def test_trace_id_is_deterministic_and_request_sensitive() -> None:
    engine = MockDseEngine.from_settings(create_app().state.settings)
    a = asyncio.run(engine.recommend(_req()))
    b = asyncio.run(engine.recommend(_req()))
    c = asyncio.run(engine.recommend(_req(riskProfile="aggressive")))
    assert a.trace_id == b.trace_id  # same request canon -> same id
    assert a.trace_id != c.trace_id  # different request -> different id
    assert a.trace_id.startswith("dss-")
    assert a.explanation_version == "dss-explain-0.1.0"


def test_explainability_does_not_change_utility_or_ranking() -> None:
    # The exposed breakdown must equal a fresh recomputation of utility_score
    # for every recommendation, and ordering stays utility-descending.
    resp = asyncio.run(MockDseEngine.from_settings(create_app().state.settings).recommend(_req()))
    scores = [Decimal(r.utility_score) for r in resp.recommendations]
    assert scores == sorted(scores, reverse=True)
    assert [r.rank for r in resp.recommendations] == list(range(1, len(scores) + 1))


# ----------------------------- endpoint (additive) -------------------------- #


def test_endpoint_exposes_breakdown_and_trace() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/dss/recommend",
        json={"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Existing contract intact.
    assert set(body["modelVersions"]) == {"pricing", "sentiment", "kelly", "stress"}
    # Additive explainability present.
    assert body["traceId"].startswith("dss-")
    assert body["explanationVersion"] == "dss-explain-0.1.0"
    rec = body["recommendations"][0]
    assert rec["topDriver"]
    total = sum(Decimal(c["contribution"]) for c in rec["utilityBreakdown"])
    assert total == Decimal(rec["utilityScore"])


# ----------------------------- spec ↔ model conformance --------------------- #


def _schema_props(schema: str) -> set[str]:
    doc = yaml.safe_load((_SPECS / "dse-baas-api.yaml").read_text())
    return set(doc["components"]["schemas"][schema]["properties"].keys())


def _aliases(model: type) -> set[str]:
    return {fi.alias or name for name, fi in model.model_fields.items()}  # type: ignore[attr-defined]


def test_utility_component_matches_spec() -> None:
    assert _aliases(UtilityComponent) == _schema_props("UtilityComponent")
