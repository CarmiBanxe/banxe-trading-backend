"""Earn advisory provider seam (T7.3) — yield rates, mock default.

Advisory-only (ADR-084/085): yields are estimates/simulations, NOT a promise of
return. NO execution, NO keys, NO network. Real StakeKit / Aave-style providers
are OPERATOR-GATED future sprints behind the same ``EarnRatesProvider`` Protocol.
"""

from .providers import (
    EarnRatesProvider,
    MockEarnRatesProvider,
    build_earn_provider,
)

__all__ = [
    "EarnRatesProvider",
    "MockEarnRatesProvider",
    "build_earn_provider",
]
