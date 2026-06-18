"""M1.5 — earn advisory analytics status enrichment (additive, advisory, mock-safe).

characterization: advisory_status filled for typical earn alternatives via the single
EarnAdvisoryStatus source-of-truth; contract: EarnMetrics frozen + existing consumers
(EarnAlternative/AnalyticsContext) compatible without the new field; negative: fail-closed
(None, never a fake value) when status is not determinable.
"""
from __future__ import annotations

import asyncio

from banxe_trading_backend.dse import AnalyticsContext, EarnAlternative, RecommendRequest
from banxe_trading_backend.dse.models import EarnMetrics
from banxe_trading_backend.earn import (
    EarnAdvisoryStatus,
    MockEarnRatesCatalog,
    MockEarnRatesProvider,
)
from banxe_trading_backend.risk import MockRiskGreeksProvider
from banxe_trading_backend.services.dss_analytics_enrichment import (
    DseAnalyticsEnrichmentService,
    _advisory_status,
)


def _enrichment() -> DseAnalyticsEnrichmentService:
    return DseAnalyticsEnrichmentService(
        greeks_provider=MockRiskGreeksProvider(),
        earn_catalog=MockEarnRatesCatalog(MockEarnRatesProvider()),
    )


def _req() -> RecommendRequest:
    return RecommendRequest.model_validate(
        {
            "asset": "BTCUSDT",
            "portfolioValueUsd": "10000",
            "currentPositions": [{"asset": "BTCUSDT", "sizeUsd": "8000", "side": "long"}],
            "riskProfile": "aggressive",
        }
    )


# ---- characterization: advisory_status filled from the single SoT ----------------

def test_earn_alternatives_carry_advisory_status_from_sot() -> None:
    ctx = asyncio.run(_enrichment().context(_req()))
    assert isinstance(ctx, AnalyticsContext)
    assert ctx.earn_alternatives
    for alt in ctx.earn_alternatives:
        assert alt.advisory_status == EarnAdvisoryStatus.NORMAL.value
        # value comes from the EarnAdvisoryStatus SoT (a valid member), not a duplicated literal
        assert alt.advisory_status in {s.value for s in EarnAdvisoryStatus}


def test_advisory_status_helper_returns_sot_value_for_wellformed_card() -> None:
    class _Card:
        asset = "USDC"
        apy_pct = "5.0000"

    assert _advisory_status(_Card()) == EarnAdvisoryStatus.NORMAL.value


# ---- contract: frozen EarnMetrics + additive/optional for existing consumers ------

def test_earnmetrics_contract_unchanged() -> None:
    assert set(EarnMetrics.model_fields.keys()) == {
        "current_yield_pct", "protocol", "chain", "lockup_days",
        "variable_rate", "risk_summary",
    }


def test_earn_alternative_additive_optional_back_compatible() -> None:
    # old consumers construct EarnAlternative WITHOUT advisory_status -> defaults to None
    alt = EarnAlternative(
        asset="BTC", protocol="mock-stakekit", apy_pct="3.5000",
        lockup_days=7, risk_band="medium", source="sandbox-mock",
    )
    assert alt.advisory_status is None
    # and AnalyticsContext still composes with such alternatives
    ctx = AnalyticsContext(earn_alternatives=[alt], analytics_version="t", source="sandbox-mock")
    assert ctx.earn_alternatives[0].advisory_status is None


# ---- negative / fail-closed ------------------------------------------------------

def test_advisory_status_fail_closed_returns_none_not_fake() -> None:
    class _Empty:
        asset = None
        apy_pct = None

    assert _advisory_status(_Empty()) is None
    assert _advisory_status(object()) is None  # missing attributes entirely
