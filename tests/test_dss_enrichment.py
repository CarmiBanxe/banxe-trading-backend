"""DSE internal analytics enrichment (T7.6) — additive, advisory, sandbox-mock.

No network. Covers: enrichment present with portfolio context, graceful absence
without it, Greeks-derived risk notes + earn-derived alternatives, additive
contract (no break for existing consumers), and spec ↔ model conformance for the
new optional schemas. The enrichment is explanation-only — ranking is unchanged.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.dse import (
    AnalyticsContext,
    EarnAlternative,
    GreeksSummary,
    MockDseEngine,
    RecommendRequest,
)
from banxe_trading_backend.dse.engine import MockDseEngine as Engine
from banxe_trading_backend.earn import MockEarnRatesCatalog, MockEarnRatesProvider
from banxe_trading_backend.risk import MockRiskGreeksProvider
from banxe_trading_backend.services.dss_analytics_enrichment import (
    DseAnalyticsEnrichmentService,
)

_SPECS = Path(__file__).resolve().parents[1] / "docs" / "specs"


def _enrichment() -> DseAnalyticsEnrichmentService:
    return DseAnalyticsEnrichmentService(
        greeks_provider=MockRiskGreeksProvider(),
        earn_catalog=MockEarnRatesCatalog(MockEarnRatesProvider()),
    )


def _req_with_positions() -> RecommendRequest:
    return RecommendRequest.model_validate(
        {
            "asset": "BTCUSDT",
            "portfolioValueUsd": "10000",
            "currentPositions": [{"asset": "BTCUSDT", "sizeUsd": "8000", "side": "long"}],
            "riskProfile": "aggressive",
        }
    )


# ----------------------- enrichment present / graceful ---------------------- #


def test_context_present_with_portfolio_context() -> None:
    ctx = asyncio.run(_enrichment().context(_req_with_positions()))
    assert isinstance(ctx, AnalyticsContext)
    assert ctx.source == "sandbox-mock"
    assert ctx.greeks_summary is not None
    # 8000 long / 10000 portfolio → delta 0.8 → "high" directional exposure.
    assert ctx.greeks_summary.directional_exposure == "high"
    assert Decimal(ctx.greeks_summary.greeks.delta) == Decimal("0.8000")
    assert ctx.greeks_summary.notes  # high-exposure note present
    assert ctx.earn_alternatives  # informational comparison present
    # Earn alternatives are sorted by APY descending.
    apys = [Decimal(a.apy_pct) for a in ctx.earn_alternatives]
    assert apys == sorted(apys, reverse=True)


def test_greeks_summary_degrades_without_positions() -> None:
    req = RecommendRequest.model_validate({"asset": "BTCUSDT", "portfolioValueUsd": "10000"})
    ctx = asyncio.run(_enrichment().context(req))
    # No positions → no Greeks summary, but earn alternatives still informational.
    assert ctx is not None
    assert ctx.greeks_summary is None
    assert ctx.earn_alternatives


def test_context_none_when_no_providers() -> None:
    svc = DseAnalyticsEnrichmentService(greeks_provider=None, earn_catalog=None)
    assert asyncio.run(svc.context(_req_with_positions())) is None


# ----------------------- engine integration (additive) ---------------------- #


def test_engine_attaches_risk_notes_and_alternatives() -> None:
    engine: MockDseEngine = Engine(enrichment=_enrichment())
    resp = asyncio.run(engine.recommend(_req_with_positions()))
    assert resp.analytics_context is not None
    by_type = {r.action.type.value: r for r in resp.recommendations}
    # Tradable (spot/perp) ideas carry Greeks-derived risk notes.
    assert by_type["OPEN_LONG"].risk_notes
    assert any("directional exposure" in n.lower() for n in by_type["OPEN_LONG"].risk_notes)
    # Capital-preservation actions carry informational earn alternatives.
    assert by_type["HOLD"].alternatives
    assert all(isinstance(a, EarnAlternative) for a in by_type["HOLD"].alternatives)
    # earn alternatives are informational, never execution — no order fields.
    assert by_type["HOLD"].alternatives[0].source == "sandbox-mock"


def test_engine_without_enrichment_is_backward_compatible() -> None:
    # No enrichment service → existing contract unchanged (no new content).
    resp = asyncio.run(Engine().recommend(_req_with_positions()))
    assert resp.analytics_context is None
    for rec in resp.recommendations:
        assert rec.risk_notes is None
        assert rec.alternatives is None


def test_enrichment_does_not_reorder_ranking() -> None:
    req = _req_with_positions()
    plain = asyncio.run(Engine().recommend(req))
    enriched = asyncio.run(Engine(enrichment=_enrichment()).recommend(req))
    # Ranking + utility scores are identical — enrichment is explanation-only.
    assert [r.action.type for r in plain.recommendations] == [
        r.action.type for r in enriched.recommendations
    ]
    assert [r.utility_score for r in plain.recommendations] == [
        r.utility_score for r in enriched.recommendations
    ]


# ----------------------- endpoint: additive, no break ----------------------- #


def test_recommend_endpoint_exposes_analytics_context() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/dss/recommend",
        json={
            "asset": "BTCUSDT",
            "portfolioValueUsd": "10000",
            "currentPositions": [{"asset": "BTCUSDT", "sizeUsd": "8000", "side": "long"}],
            "riskProfile": "balanced",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # Existing contract intact.
    assert body["recommendations"] and body["disclaimer"]
    assert set(body["modelVersions"]) == {"pricing", "sentiment", "kelly", "stress"}
    # Additive enrichment present + flagged sandbox-mock.
    ctx = body["analyticsContext"]
    assert ctx["source"] == "sandbox-mock"
    assert ctx["greeksSummary"]["directionalExposure"] == "high"
    assert ctx["earnAlternatives"]


def test_recommend_endpoint_no_positions_still_valid() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/dss/recommend",
        json={"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Previously-valid call stays valid; greeksSummary degrades to null.
    assert body["analyticsContext"]["greeksSummary"] is None


# ----------------------- spec ↔ model conformance --------------------------- #


def _schema_props(schema: str) -> set[str]:
    doc = yaml.safe_load((_SPECS / "dse-baas-api.yaml").read_text())
    return set(doc["components"]["schemas"][schema]["properties"].keys())


def _aliases(model: type) -> set[str]:
    return {fi.alias or name for name, fi in model.model_fields.items()}  # type: ignore[attr-defined]


def test_enrichment_models_match_spec() -> None:
    for model, schema in [
        (EarnAlternative, "EarnAlternative"),
        (GreeksSummary, "GreeksSummary"),
        (AnalyticsContext, "AnalyticsContext"),
    ]:
        assert _aliases(model) == _schema_props(schema), f"{schema} mismatch"
