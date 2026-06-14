"""Utility score U_a (T7.1) — pure Decimal (I-01, no float).

U_a = w1*ER - w2*sigma - w3*VaR99 - w4*DD + w5*Liq

ER/sigma/VaR99/DD are fractions (e.g. 0.05 = 5%); Liq is a [0,1] score. Weights
are resolved from the risk profile (see profiles.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import UtilityWeights


@dataclass(frozen=True)
class CandidateMetrics:
    """Raw (fraction) candidate metrics used to compute utility."""

    expected_return: Decimal
    volatility: Decimal
    var99: Decimal
    max_drawdown: Decimal
    liquidity: Decimal  # [0, 1]


def utility_score(metrics: CandidateMetrics, weights: UtilityWeights) -> Decimal:
    return (
        Decimal(weights.w1_expected_return) * metrics.expected_return
        - Decimal(weights.w2_volatility) * metrics.volatility
        - Decimal(weights.w3_var99) * metrics.var99
        - Decimal(weights.w4_drawdown) * metrics.max_drawdown
        + Decimal(weights.w5_liquidity) * metrics.liquidity
    )


@dataclass(frozen=True)
class UtilityTerm:
    """One signed term of the utility decomposition (explainability, T7.7)."""

    factor: str
    value: Decimal  # the metric value fed into utility (fraction or [0,1] score)
    weight: Decimal  # the resolved profile weight
    contribution: Decimal  # signed contribution to U_a (sign folds the +/- term)
    direction: str  # "positive" | "negative"


def utility_components(metrics: CandidateMetrics, weights: UtilityWeights) -> list[UtilityTerm]:
    """Decompose ``utility_score`` into its 5 signed terms (sum == the score).

    Pure / explainability-only: this exposes the EXISTING math (it does not change
    utility or ranking). ``sum(t.contribution ...) == utility_score(metrics, weights)``.
    """
    w1 = Decimal(weights.w1_expected_return)
    w2 = Decimal(weights.w2_volatility)
    w3 = Decimal(weights.w3_var99)
    w4 = Decimal(weights.w4_drawdown)
    w5 = Decimal(weights.w5_liquidity)
    return [
        UtilityTerm("expectedReturn", metrics.expected_return, w1,
                    w1 * metrics.expected_return, "positive"),
        UtilityTerm("volatility", metrics.volatility, w2,
                    -(w2 * metrics.volatility), "negative"),
        UtilityTerm("var99", metrics.var99, w3,
                    -(w3 * metrics.var99), "negative"),
        UtilityTerm("drawdown", metrics.max_drawdown, w4,
                    -(w4 * metrics.max_drawdown), "negative"),
        UtilityTerm("liquidity", metrics.liquidity, w5,
                    w5 * metrics.liquidity, "positive"),
    ]
