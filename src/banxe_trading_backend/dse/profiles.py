"""Risk-profile utility weight presets (T7.1).

Three preset profiles plus a custom path (user-supplied weights). Conservative
penalises risk (volatility / VaR / drawdown) heavily; Aggressive favours expected
return. All weights are Decimal strings (I-01).
"""

from __future__ import annotations

from .models import RiskProfile, UtilityWeights

CONSERVATIVE = UtilityWeights(
    w1_expected_return="0.5",
    w2_volatility="1.5",
    w3_var99="2.0",
    w4_drawdown="1.5",
    w5_liquidity="0.5",
)
BALANCED = UtilityWeights(
    w1_expected_return="1.0",
    w2_volatility="1.0",
    w3_var99="1.0",
    w4_drawdown="1.0",
    w5_liquidity="1.0",
)
AGGRESSIVE = UtilityWeights(
    w1_expected_return="2.0",
    w2_volatility="0.5",
    w3_var99="0.5",
    w4_drawdown="0.5",
    w5_liquidity="1.0",
)

_PRESETS = {
    RiskProfile.CONSERVATIVE: CONSERVATIVE,
    RiskProfile.BALANCED: BALANCED,
    RiskProfile.AGGRESSIVE: AGGRESSIVE,
}


def weights_for(profile: RiskProfile, custom: UtilityWeights | None) -> UtilityWeights:
    """Resolve weights: a preset, or the user's custom weights when 'custom'."""
    if profile is RiskProfile.CUSTOM:
        if custom is None:
            raise ValueError("riskProfile 'custom' requires customWeights")
        return custom
    return _PRESETS[profile]
