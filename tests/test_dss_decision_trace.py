"""DSE opt-in sandbox decision-trace (T7.8) — observability/debug, dev-only.

No network. Covers the double gate (env flag + header), trace reconstruction
(inputs → normalized features), traceId correlation, ranking/utility invariance,
the no-secrets guarantee, and spec ↔ model conformance. Default-OFF: production
partners never receive the trace.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.dse import (
    DecisionTrace,
    DecisionTraceStep,
    MockDseEngine,
    RecommendRequest,
)

_SPECS = Path(__file__).resolve().parents[1] / "docs" / "specs"


def _req() -> RecommendRequest:
    return RecommendRequest.model_validate(
        {
            "asset": "BTCUSDT",
            "portfolioValueUsd": "10000",
            "riskProfile": "balanced",
            "currentPositions": [{"asset": "BTCUSDT", "sizeUsd": "8000", "side": "long"}],
        }
    )


def _engine(debug_enabled: bool) -> MockDseEngine:
    return MockDseEngine.from_settings(Settings(dse_debug_enabled=debug_enabled))


# ------------------------------ the double gate ----------------------------- #


def test_no_trace_when_env_flag_off_even_if_requested() -> None:
    resp = asyncio.run(_engine(debug_enabled=False).recommend(_req(), debug=True))
    assert resp.decision_trace is None


def test_no_trace_when_not_requested_even_if_env_on() -> None:
    resp = asyncio.run(_engine(debug_enabled=True).recommend(_req(), debug=False))
    assert resp.decision_trace is None


def test_trace_present_only_when_both_gates_open() -> None:
    resp = asyncio.run(_engine(debug_enabled=True).recommend(_req(), debug=True))
    assert isinstance(resp.decision_trace, DecisionTrace)
    assert resp.decision_trace.trace_id == resp.trace_id  # correlation by traceId


# ------------------------- reconstruction of the path ----------------------- #


def test_trace_reconstructs_inputs_and_features() -> None:
    resp = asyncio.run(_engine(debug_enabled=True).recommend(_req(), debug=True))
    trace = resp.decision_trace
    assert trace is not None
    # One step per candidate, ranked order matches the recommendations.
    assert [s.rank for s in trace.steps] == [r.rank for r in resp.recommendations]
    assert [s.action_type for s in trace.steps] == [
        r.action.type.value for r in resp.recommendations
    ]
    # Earn fold is visible: STAKE effective ER = raw ER + earn yield (mock).
    stake = next(s for s in trace.steps if s.action_type == "STAKE")
    assert stake.earn_yield_pct is not None
    expected = Decimal(stake.raw_expected_return) + Decimal(stake.earn_yield_pct) / 100
    assert Decimal(stake.effective_expected_return) == expected
    # VaR99 provenance is traceable; with the app default a risk provider is wired.
    assert stake.var99_source == "risk-provider"
    # Each step's utilityScore echoes the recommendation's score.
    by_type = {r.action.type.value: r for r in resp.recommendations}
    for s in trace.steps:
        assert s.utility_score == by_type[s.action_type].utility_score


def test_trace_var99_source_fallback_without_risk_provider() -> None:
    eng = MockDseEngine(debug_enabled=True, risk_provider=None)
    resp = asyncio.run(eng.recommend(_req(), debug=True))
    assert resp.decision_trace is not None
    assert all(s.var99_source == "candidate-fallback" for s in resp.decision_trace.steps)


def test_trace_metadata_carries_no_secrets() -> None:
    resp = asyncio.run(_engine(debug_enabled=True).recommend(_req(), debug=True))
    trace = resp.decision_trace
    assert trace is not None
    # Provider fields are class names (or 'none'), never credentials/endpoints.
    assert trace.risk_provider == "MockRiskMetricsProvider"
    assert "Mock" in trace.sentiment_provider
    assert trace.weights is not None and trace.note
    # Scan the trace payload (minus the human disclaimer, which names these words)
    # for any leaked credential/endpoint material.
    blob = trace.model_dump_json(exclude={"note"}).lower()
    for forbidden in ("key", "secret", "token", "password", "http://", "https://"):
        assert forbidden not in blob


# ----------------------- invariance: utility/ranking ------------------------ #


def test_trace_does_not_change_utility_or_ranking() -> None:
    eng = _engine(debug_enabled=True)
    plain = asyncio.run(eng.recommend(_req(), debug=False))
    traced = asyncio.run(eng.recommend(_req(), debug=True))
    assert [r.action.type for r in plain.recommendations] == [
        r.action.type for r in traced.recommendations
    ]
    assert [r.utility_score for r in plain.recommendations] == [
        r.utility_score for r in traced.recommendations
    ]


# ----------------------------- endpoint (header) ---------------------------- #


def test_endpoint_default_app_never_returns_trace() -> None:
    # Default app: env flag OFF -> header is ignored, no trace (prod-safe).
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/dss/recommend",
        json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"},
        headers={"X-Banxe-Dse-Debug": "true"},
    )
    assert resp.status_code == 200
    assert resp.json()["decisionTrace"] is None


def test_endpoint_emits_trace_with_flag_and_header() -> None:
    client = TestClient(create_app(Settings(dse_debug_enabled=True)))
    # No header -> still no trace.
    plain = client.post(
        "/api/v1/dss/recommend", json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"}
    )
    assert plain.json()["decisionTrace"] is None
    # Header opts in -> trace present.
    resp = client.post(
        "/api/v1/dss/recommend",
        json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"},
        headers={"X-Banxe-Dse-Debug": "1"},
    )
    body = resp.json()
    assert body["decisionTrace"]["traceId"] == body["traceId"]
    assert len(body["decisionTrace"]["steps"]) == 6


# ----------------------------- spec ↔ model --------------------------------- #


def _schema_props(schema: str) -> set[str]:
    doc = yaml.safe_load((_SPECS / "dse-baas-api.yaml").read_text())
    return set(doc["components"]["schemas"][schema]["properties"].keys())


def _aliases(model: type) -> set[str]:
    return {fi.alias or name for name, fi in model.model_fields.items()}  # type: ignore[attr-defined]


def test_trace_models_match_spec() -> None:
    assert _aliases(DecisionTraceStep) == _schema_props("DecisionTraceStep")
    assert _aliases(DecisionTrace) == _schema_props("DecisionTrace")
