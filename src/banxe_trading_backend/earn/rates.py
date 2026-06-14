"""Earn rate comparison — read-only BaaS sandbox surface (T7.5).

Backs ``GET /v1/earn/rates``: a current-yield comparison ("rate cards") across a
basket of assets. ADVISORY-ONLY, sandbox/mock data flagged ``source:
"sandbox-mock"`` — yields are estimates / simulations, NOT a promise of return,
NO stake/unstake, NO execution, NO keys, NO network. Real StakeKit / Aave-style
catalogues register later behind the same Protocol (operator-gated).
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from banxe_trading_backend.earn.providers import EarnRatesProvider
from banxe_trading_backend.models import CamelModel, DecimalStr
from banxe_trading_backend.risk.greeks import SANDBOX_MOCK

#: Default comparison basket when the caller does not pass `assets`.
DEFAULT_BASKET = ("BTC", "ETH", "USDC")

_RATES_DISCLAIMER = (
    "Advisory analytics only — sandbox mock yields, estimates / simulations and "
    "NOT a promise of return, NOT investment advice and NOT execution (no stake / "
    "unstake). MiCA / MiFID II: analytics, not execution. Self-custodial."
)


class RiskBand(str, Enum):
    """Qualitative earn risk band (advisory)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Deterministic qualitative band per asset base (mock; advisory only).
_BAND_BY_BASE: dict[str, RiskBand] = {
    "USDC": RiskBand.LOW,
    "USDT": RiskBand.LOW,
    "BTC": RiskBand.MEDIUM,
    "ETH": RiskBand.MEDIUM,
}


class RateCard(CamelModel):
    """A single earn rate card (advisory, sandbox-mock)."""

    asset: str
    protocol: str
    apy_pct: DecimalStr
    lockup_days: int
    variable_rate: bool
    risk_band: RiskBand
    source: str


class EarnRatesResponse(CamelModel):
    """Read-only yield comparison across the requested basket (sandbox-mock)."""

    rates: list[RateCard]
    source: str
    as_of: str
    disclaimer: str


@runtime_checkable
class EarnRatesCatalog(Protocol):
    """Yield comparison across a basket of assets (advisory; read-only)."""

    async def list_rates(self, assets: list[str]) -> list[RateCard]: ...


def _band_for(asset: str) -> RiskBand:
    upper = asset.upper()
    for base, band in _BAND_BY_BASE.items():
        if upper.startswith(base):
            return band
    return RiskBand.HIGH


class MockEarnRatesCatalog:
    """Compose rate cards from the deterministic mock earn provider."""

    def __init__(self, provider: EarnRatesProvider) -> None:
        self._provider = provider

    async def list_rates(self, assets: list[str]) -> list[RateCard]:
        cards: list[RateCard] = []
        for asset in assets:
            metrics = await self._provider.get_earn_metrics(asset)
            cards.append(
                RateCard(
                    asset=asset,
                    protocol=metrics.protocol,
                    apy_pct=metrics.current_yield_pct,
                    lockup_days=metrics.lockup_days,
                    variable_rate=metrics.variable_rate,
                    risk_band=_band_for(asset),
                    source=SANDBOX_MOCK,
                )
            )
        return cards


def build_earn_rates_catalog(name: str, provider: EarnRatesProvider) -> EarnRatesCatalog:
    """Resolve an earn rates catalogue by name. Only 'mock' is wired."""
    if name == "mock":
        return MockEarnRatesCatalog(provider)
    # Real StakeKit / Aave-style catalogues are OPERATOR-GATED (keys/network).
    raise ValueError(
        f"earn rates catalog {name!r} is not wired (operator-gated); only 'mock'"
    )


async def earn_rates(
    catalog: EarnRatesCatalog, *, assets: list[str], now: str
) -> EarnRatesResponse:
    """Assemble the read-only advisory comparison (sandbox-mock flagged)."""
    basket = assets or list(DEFAULT_BASKET)
    cards = await catalog.list_rates(basket)
    return EarnRatesResponse(
        rates=cards,
        source=SANDBOX_MOCK,
        as_of=now,
        disclaimer=_RATES_DISCLAIMER,
    )
