"""Risk metrics providers (T7.3) — deterministic mock, no network/keys.

VaR99 is parametric (z99 × volatility); Greeks are simple Delta/Gamma/Theta-style
stubs per action category; PnL is computed from the request's positions in the
asset. All Decimal (I-01). Real providers register behind ``RiskMetricsProvider``
(operator-gated).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from banxe_trading_backend.dse.models import (
    Action,
    ActionCategory,
    Greeks,
    RecommendRequest,
    RiskMetrics,
)
from banxe_trading_backend.dse.utility import CandidateMetrics

# 99% one-tailed normal quantile (parametric VaR multiplier).
_Z99 = Decimal("2.3263")

# Simple, deterministic Delta/Gamma/Theta-style Greeks per action category.
_GREEKS_BY_CATEGORY: dict[ActionCategory, Greeks] = {
    ActionCategory.SPOT: Greeks(delta="1.0", gamma="0", vega="0", theta="0", rho="0.01"),
    ActionCategory.PERP: Greeks(delta="1.0", gamma="0.02", vega="0", theta="-0.01", rho="0.02"),
    ActionCategory.EARN: Greeks(delta="0.2", gamma="0", vega="0", theta="0.01", rho="0"),
    ActionCategory.RISK: Greeks(delta="-1.0", gamma="0.05", vega="0.10", theta="-0.02", rho="0"),
    ActionCategory.META: Greeks(delta="0", gamma="0", vega="0", theta="0", rho="0"),
}

_SIDE_SIGN = {"long": Decimal(1), "spot": Decimal(1), "short": Decimal(-1)}


def _pct(value: Decimal) -> str:
    return str((value * 100).quantize(Decimal("0.0001")))


def _usd(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


@runtime_checkable
class RiskMetricsProvider(Protocol):
    """Aggregated Greeks / VaR / PnL for a candidate action (advisory)."""

    async def get_risk_metrics(
        self, request: RecommendRequest, action: Action, candidate: CandidateMetrics
    ) -> RiskMetrics: ...


class MockRiskMetricsProvider:
    """Deterministic risk metrics — parametric VaR99, stub Greeks, position PnL."""

    async def get_risk_metrics(
        self, request: RecommendRequest, action: Action, candidate: CandidateMetrics
    ) -> RiskMetrics:
        greeks = _GREEKS_BY_CATEGORY[action.category]
        # Parametric VaR99 = z99 × volatility (fraction).
        var99 = _Z99 * candidate.volatility
        # Unrealized PnL from positions in this asset; stub current move = ER.
        pnl_usd = Decimal(0)
        for pos in request.current_positions:
            if pos.asset == request.asset:
                sign = _SIDE_SIGN.get(pos.side, Decimal(1))
                pnl_usd += Decimal(pos.size_usd) * candidate.expected_return * sign
        portfolio = Decimal(request.portfolio_value_usd)
        pnl_pct = (pnl_usd / portfolio) if portfolio > 0 else Decimal(0)
        return RiskMetrics(
            greeks=greeks,
            var99_pct=_pct(var99),
            dd_pct=_pct(candidate.max_drawdown),
            unrealized_pnl_pct=_pct(pnl_pct),
            unrealized_pnl_usd=_usd(pnl_usd),
            liquidity_score=str(candidate.liquidity.quantize(Decimal("0.0001"))),
        )


def build_risk_provider(name: str) -> RiskMetricsProvider:
    """Resolve a risk provider by name. Only 'mock' is wired (default)."""
    if name == "mock":
        return MockRiskMetricsProvider()
    # Real risk-data providers are OPERATOR-GATED future sprints (keys/network).
    raise ValueError(
        f"risk provider {name!r} is not wired (operator-gated); only 'mock' is available"
    )
