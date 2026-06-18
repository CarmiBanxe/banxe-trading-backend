"""Earn advisory read-only statement / summary (M1.6, mock-safe).

Composes the ALREADY-MIGRATED advisory sources into one read-only per-asset statement:
- RateCard (earn/rates, via EarnRatesCatalog): asset/protocol/apy/lockup/variable/risk_band;
- EarnMetrics (earn/crypto_earn|providers): fee/product detail in risk_summary;
- EarnAdvisoryStatus (earn/status, M1.4): advisory lifecycle.

It is a NEW additive view DTO + endpoint. It does NOT mutate EarnRatesResponse / EarnMetrics /
AnalyticsContext (all frozen) and introduces NO second rates/analytics source-of-truth.

READ-ONLY / advisory: NO live balances, NO positions, NO execution state, NO payments, NO fund
movement. Deterministic mock composition; fail-closed (skip / None, never a fake value) when an
upstream advisory source is unavailable.
"""
from __future__ import annotations

from banxe_trading_backend.earn.providers import EarnRatesProvider
from banxe_trading_backend.earn.rates import DEFAULT_BASKET, EarnRatesCatalog, RateCard
from banxe_trading_backend.earn.status import EarnAdvisoryStatus
from banxe_trading_backend.models import CamelModel, DecimalStr
from banxe_trading_backend.risk.greeks import SANDBOX_MOCK

_STATEMENT_DISCLAIMER = (
    "Advisory read-only earn statement (sandbox-mock): yields/fees are estimates, NOT a "
    "promise of return; NO live balances, positions, execution, or payments."
)


class EarnStatement(CamelModel):
    """Per-asset advisory earn statement (read-only; composed, not a live position)."""

    asset: str
    protocol: str
    current_yield_pct: DecimalStr
    lockup_days: int
    variable_rate: bool
    risk_band: str
    fee_summary: str
    advisory_status: str | None
    source: str


class EarnStatementResponse(CamelModel):
    """Read-only advisory earn statements across the requested basket (sandbox-mock)."""

    statements: list[EarnStatement]
    source: str
    as_of: str
    disclaimer: str


def _advisory_status() -> str | None:
    """Advisory lifecycle for an available earn product (EarnAdvisoryStatus SoT; fail-closed)."""
    try:
        return EarnAdvisoryStatus.NORMAL.value
    except Exception:
        return None


async def earn_statement(
    catalog: EarnRatesCatalog,
    provider: EarnRatesProvider,
    *,
    assets: list[str],
    now: str,
) -> EarnStatementResponse:
    """Compose a read-only advisory statement from existing advisory sources (fail-closed)."""
    basket = assets or list(DEFAULT_BASKET)
    cards: list[RateCard] = await catalog.list_rates(basket)
    statements: list[EarnStatement] = []
    for card in cards:
        try:
            metrics = await provider.get_earn_metrics(card.asset)
            fee_summary = metrics.risk_summary
        except Exception:
            continue
        statements.append(
            EarnStatement(
                asset=card.asset,
                protocol=card.protocol,
                current_yield_pct=card.apy_pct,
                lockup_days=card.lockup_days,
                variable_rate=card.variable_rate,
                risk_band=card.risk_band.value,
                fee_summary=fee_summary,
                advisory_status=_advisory_status(),
                source=SANDBOX_MOCK,
            )
        )
    return EarnStatementResponse(
        statements=statements,
        source=SANDBOX_MOCK,
        as_of=now,
        disclaimer=_STATEMENT_DISCLAIMER,
    )
