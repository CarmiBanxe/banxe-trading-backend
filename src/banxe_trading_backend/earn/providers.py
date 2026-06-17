"""Earn rates providers (T7.3) — deterministic mock, no network/keys.

Returns a stable set of StakeKit/Aave-style yield scenarios per asset. Yields are
advisory estimates only. Real providers register behind ``EarnRatesProvider``
(operator-gated).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from banxe_trading_backend.dse.models import EarnMetrics

# Asset base → stable earn scenario (mock; not a promise of return).
_EARN_BY_BASE: list[tuple[str, EarnMetrics]] = [
    (
        "BTC",
        EarnMetrics(
            current_yield_pct="3.5000",
            protocol="mock-stakekit",
            chain="ethereum",
            lockup_days=7,
            variable_rate=True,
            risk_summary="Wrapped/liquid staking; smart-contract + slashing risk.",
        ),
    ),
    (
        "ETH",
        EarnMetrics(
            current_yield_pct="4.2000",
            protocol="mock-liquid-staking",
            chain="ethereum",
            lockup_days=0,
            variable_rate=True,
            risk_summary="Liquid staking; validator + protocol risk.",
        ),
    ),
    (
        "USDC",
        EarnMetrics(
            current_yield_pct="5.0000",
            protocol="mock-lending",
            chain="ethereum",
            lockup_days=0,
            variable_rate=True,
            risk_summary="Lending; variable rate, liquidation-cascade risk.",
        ),
    ),
]
_DEFAULT_EARN = EarnMetrics(
    current_yield_pct="2.0000",
    protocol="mock-generic",
    chain="ethereum",
    lockup_days=0,
    variable_rate=True,
    risk_summary="Generic variable-rate yield; estimate only.",
)


@runtime_checkable
class EarnRatesProvider(Protocol):
    """Yield scenario for an asset (advisory; not a promise of return)."""

    async def get_earn_metrics(self, asset: str) -> EarnMetrics: ...


class MockEarnRatesProvider:
    """Deterministic mock earn rates — no network."""

    async def get_earn_metrics(self, asset: str) -> EarnMetrics:
        upper = asset.upper()
        for base, metrics in _EARN_BY_BASE:
            if upper.startswith(base):
                return metrics
        return _DEFAULT_EARN


def build_earn_provider(name: str) -> EarnRatesProvider:
    """Resolve an earn provider by name. Only 'mock' is wired (default)."""
    if name == "mock":
        return MockEarnRatesProvider()
    if name == "crypto-earn":
        # M1.2: legacy banxe-crypto-earn product/fee structure as advisory rates
        # (mock-safe; no live coupling). Extends the seam, default stays "mock".
        from banxe_trading_backend.earn.crypto_earn import CryptoEarnRatesProvider
        return CryptoEarnRatesProvider()
    # Real StakeKit/Aave-style providers are OPERATOR-GATED (keys/network).
    raise ValueError(
        f"earn provider {name!r} is not wired (operator-gated); only 'mock' is available"
    )
