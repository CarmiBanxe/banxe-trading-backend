"""Risk advisory provider seam (T7.3) — Greeks / VaR / PnL, mock default.

Advisory-only (ADR-084/085): produces explainable risk *estimates* that feed the
DSE utility and the terminal risk snapshot. NO execution, NO keys, NO network.
The real risk-data provider is an OPERATOR-GATED future sprint behind the same
``RiskMetricsProvider`` Protocol. Simple, stable models only (Delta/Gamma/Theta
stub Greeks, parametric VaR99, position-based PnL).
"""

from .greeks import (
    MockRiskGreeksProvider,
    PortfolioGreeksResponse,
    RiskGreeksProvider,
    build_risk_greeks_provider,
    portfolio_greeks,
)
from .providers import (
    MockRiskMetricsProvider,
    RiskMetricsProvider,
    build_risk_provider,
)

__all__ = [
    "RiskMetricsProvider",
    "MockRiskMetricsProvider",
    "build_risk_provider",
    "RiskGreeksProvider",
    "MockRiskGreeksProvider",
    "PortfolioGreeksResponse",
    "build_risk_greeks_provider",
    "portfolio_greeks",
]
