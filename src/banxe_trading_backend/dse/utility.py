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
