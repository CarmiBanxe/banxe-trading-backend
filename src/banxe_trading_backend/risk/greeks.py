"""Portfolio-level Greeks — read-only BaaS sandbox surface (T7.5).

Backs ``GET /v1/risk/greeks``: portfolio-level Delta/Gamma/Vega/Theta/Rho for a
target asset / net notional. ADVISORY-ONLY, sandbox/mock data — the values are
deterministic illustrations flagged ``source: "sandbox-mock"``, NOT a calibrated
risk model and NOT execution. The real model registers later behind
``RiskGreeksProvider`` (operator-gated) WITHOUT changing this public contract.

No network, no keys, light deterministic math (latency target is trivially met).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from banxe_trading_backend.dse.models import Greeks
from banxe_trading_backend.models import CamelModel, DecimalStr

#: Sandbox marker carried by every read-only mock response (T7.5).
SANDBOX_MOCK = "sandbox-mock"

_SIDE_SIGN = {"long": Decimal(1), "spot": Decimal(1), "short": Decimal(-1)}

_GREEKS_DISCLAIMER = (
    "Advisory analytics only — sandbox mock data, NOT a calibrated risk model, "
    "NOT investment advice and NOT execution (MiCA / MiFID II). Self-custodial."
)


class PortfolioGreeksResponse(CamelModel):
    """Portfolio-level Greeks for a target asset (advisory, sandbox-mock)."""

    asset: str
    notional_usd: DecimalStr
    side: str
    greeks: Greeks
    source: str
    as_of: str
    disclaimer: str


@runtime_checkable
class RiskGreeksProvider(Protocol):
    """Portfolio-level Greeks for a target asset / net notional (advisory)."""

    def get_portfolio_greeks(
        self, asset: str, notional_usd: Decimal, side: str, portfolio_usd: Decimal
    ) -> Greeks: ...


def _q(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))


class MockRiskGreeksProvider:
    """Deterministic, light mock Greeks — no network, no calibration."""

    def get_portfolio_greeks(
        self, asset: str, notional_usd: Decimal, side: str, portfolio_usd: Decimal
    ) -> Greeks:
        sign = _SIDE_SIGN.get(side, Decimal(1))
        denom = portfolio_usd if portfolio_usd > 0 else (notional_usd or Decimal(1))
        # Directional exposure fraction (signed); the rest are simple proxies.
        delta = (notional_usd * sign) / denom
        abs_frac = abs(notional_usd) / denom
        return Greeks(
            delta=_q(delta),
            gamma=_q(Decimal("0.02") * abs_frac),
            vega=_q(Decimal("0.10") * abs_frac),
            theta=_q(Decimal("-0.01") * abs_frac),
            rho=_q(Decimal("0.01") * delta),
        )


def build_risk_greeks_provider(name: str) -> RiskGreeksProvider:
    """Resolve a portfolio-Greeks provider by name. Only 'mock' is wired."""
    if name == "mock":
        return MockRiskGreeksProvider()
    # Real risk-model providers are OPERATOR-GATED (keys/network/calibration).
    raise ValueError(
        f"risk greeks provider {name!r} is not wired (operator-gated); only 'mock'"
    )


def portfolio_greeks(
    provider: RiskGreeksProvider,
    *,
    asset: str,
    notional_usd: Decimal,
    side: str,
    portfolio_usd: Decimal,
    now: str,
) -> PortfolioGreeksResponse:
    """Assemble the read-only advisory response (sandbox-mock flagged)."""
    greeks = provider.get_portfolio_greeks(asset, notional_usd, side, portfolio_usd)
    return PortfolioGreeksResponse(
        asset=asset,
        notional_usd=str(notional_usd.quantize(Decimal("0.01"))),
        side=side,
        greeks=greeks,
        source=SANDBOX_MOCK,
        as_of=now,
        disclaimer=_GREEKS_DISCLAIMER,
    )
