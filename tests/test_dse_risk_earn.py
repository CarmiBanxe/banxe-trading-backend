"""DSE Risk & Earn advisory surfacing (T7.3) — mock default, no network."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from banxe_trading_backend.config import Settings
from banxe_trading_backend.dse import (
    Action,
    ActionCategory,
    ActionType,
    MockDseEngine,
    Position,
    RecommendRequest,
)
from banxe_trading_backend.dse.utility import CandidateMetrics
from banxe_trading_backend.earn import (
    EarnRatesProvider,
    MockEarnRatesProvider,
    build_earn_provider,
)
from banxe_trading_backend.risk import (
    MockRiskMetricsProvider,
    RiskMetricsProvider,
    build_risk_provider,
)


def _req(**kw: object) -> RecommendRequest:
    return RecommendRequest(asset="BTCUSDT", portfolio_value_usd="10000", **kw)  # type: ignore[arg-type]


def _candidate() -> CandidateMetrics:
    return CandidateMetrics(
        Decimal("0.08"), Decimal("0.04"), Decimal("0.06"), Decimal("0.05"), Decimal("0.90")
    )


# --------------------------- providers --------------------------------------- #


def test_providers_satisfy_protocols_and_selectors() -> None:
    assert isinstance(MockRiskMetricsProvider(), RiskMetricsProvider)
    assert isinstance(MockEarnRatesProvider(), EarnRatesProvider)
    assert isinstance(build_risk_provider("mock"), MockRiskMetricsProvider)
    assert isinstance(build_earn_provider("mock"), MockEarnRatesProvider)
    with pytest.raises(ValueError, match="not wired"):
        build_risk_provider("realrisk")
    with pytest.raises(ValueError, match="not wired"):
        build_earn_provider("stakekit")


def test_mock_risk_metrics_parametric_var_and_greeks() -> None:
    action = Action(type=ActionType.OPEN_LONG, category=ActionCategory.PERP, asset="BTCUSDT")
    rm = asyncio.run(MockRiskMetricsProvider().get_risk_metrics(_req(), action, _candidate()))
    # Parametric VaR99 = 2.3263 × 0.04 = 0.0930… → 9.3052%
    assert rm.var99_pct == "9.3052"
    assert rm.greeks.delta == "1.0"  # delta-one perp
    assert Decimal(rm.var99_pct) > 0


def test_mock_risk_pnl_from_positions() -> None:
    action = Action(type=ActionType.OPEN_LONG, category=ActionCategory.PERP, asset="BTCUSDT")
    req = _req(current_positions=[Position(asset="BTCUSDT", size_usd="1000", side="long")])
    rm = asyncio.run(MockRiskMetricsProvider().get_risk_metrics(req, action, _candidate()))
    # PnL = 1000 × ER(0.08) × long(+1) = 80.00 USD; 80/10000 = 0.80%
    assert rm.unrealized_pnl_usd == "80.00"
    assert rm.unrealized_pnl_pct == "0.8000"


def test_mock_earn_metrics_per_asset() -> None:
    em = asyncio.run(MockEarnRatesProvider().get_earn_metrics("BTCUSDT"))
    assert em.protocol == "mock-stakekit"
    assert em.chain == "ethereum"
    assert Decimal(em.current_yield_pct) > 0
    assert em.variable_rate is True


# --------------------------- engine integration ------------------------------ #


def test_recommendations_carry_risk_metrics() -> None:
    engine = MockDseEngine.from_settings(Settings())
    resp = asyncio.run(engine.recommend(_req()))
    for rec in resp.recommendations:
        assert rec.risk_metrics is not None  # required on every recommendation
        assert Decimal(rec.risk_metrics.var99_pct) >= 0
        assert "VaR99" in rec.reasons  # reasons reference risk metrics


def test_earn_metrics_only_on_earn_actions() -> None:
    engine = MockDseEngine.from_settings(Settings())
    resp = asyncio.run(engine.recommend(_req()))
    by_type = {r.action.type: r for r in resp.recommendations}
    assert by_type[ActionType.STAKE].earn_metrics is not None  # earn action
    assert by_type[ActionType.STAKE].earn_metrics.protocol == "mock-stakekit"
    assert "Yield" in by_type[ActionType.STAKE].reasons
    assert by_type[ActionType.OPEN_LONG].earn_metrics is None  # non-earn


def test_utility_degrades_gracefully_without_providers() -> None:
    # No risk/earn providers → fallback risk metrics (candidate-derived), no earn.
    engine = MockDseEngine()  # default: no risk/earn providers
    resp = asyncio.run(engine.recommend(_req()))
    rec = next(r for r in resp.recommendations if r.action.type == ActionType.OPEN_LONG)
    assert rec.risk_metrics is not None  # fallback still populates it
    assert rec.risk_metrics.var99_pct == "6.0000"  # candidate VaR (0.06), not parametric
    assert rec.earn_metrics is None
    # Still ranked + valid (advisory unaffected by missing providers).
    scores = [Decimal(r.utility_score) for r in resp.recommendations]
    assert scores == sorted(scores, reverse=True)


def test_earn_yield_raises_stake_utility_vs_no_earn() -> None:
    base = MockDseEngine()  # no earn provider
    with_earn = MockDseEngine(earn_provider=MockEarnRatesProvider())
    stake_base = next(
        r for r in asyncio.run(base.recommend(_req())).recommendations
        if r.action.type == ActionType.STAKE
    )
    stake_earn = next(
        r for r in asyncio.run(with_earn.recommend(_req())).recommendations
        if r.action.type == ActionType.STAKE
    )
    # Earn yield folds into expected return → higher utility for the stake action.
    assert Decimal(stake_earn.utility_score) > Decimal(stake_base.utility_score)
