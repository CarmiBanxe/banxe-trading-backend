"""DSE analytics enrichment (T7.6) — internal-only, advisory, sandbox-mock.

Composes the T7.5 sandbox Risk Greeks and Earn rates services **in-process** to
enrich `POST /v1/dss/recommend` responses with explainable, additive context:
portfolio-level Greeks notes and informational earn alternatives. It adds NO new
public endpoint, NO HTTP self-calls, NO execution, NO signing — purely
explanation-oriented advisory enrichment.

Boundaries (ADR-086 follow-up, T7.6):
- Internal facade over the existing mock providers (no duplicated mock logic).
- Sandbox / mock default — no network, no keys, graceful degrade when inputs are
  absent. Values are flagged ``source: "sandbox-mock"``.
- Explanation-only: it does NOT silently re-rank; the established utility
  framework is unchanged.
"""

from __future__ import annotations

from decimal import Decimal

from banxe_trading_backend.dse.models import (
    ActionType,
    AnalyticsContext,
    EarnAlternative,
    GreeksSummary,
    Recommendation,
    RecommendRequest,
)
from banxe_trading_backend.earn.rates import DEFAULT_BASKET, EarnRatesCatalog
from banxe_trading_backend.earn.status import EarnAdvisoryStatus
from banxe_trading_backend.risk.greeks import SANDBOX_MOCK, RiskGreeksProvider

#: Traceability marker for the enrichment composition.
ANALYTICS_VERSION = "dss-analytics-enrichment-0.1.0"

# Actions where idle capital could instead sit in yield — earn alternatives are
# surfaced as a lower-risk rationale (informational only, never execution).
_CAPITAL_PRESERVATION = frozenset(
    {ActionType.HOLD, ActionType.WAIT, ActionType.HEDGE, ActionType.STAKE}
)

_HIGH_DELTA = Decimal("0.66")
_ELEVATED_DELTA = Decimal("0.33")


def _net_exposure(request: RecommendRequest) -> tuple[Decimal, str] | None:
    """Net signed USD exposure to the request asset, or None if no positions."""
    net = Decimal(0)
    matched = False
    for pos in request.current_positions:
        if pos.asset != request.asset:
            continue
        matched = True
        sign = Decimal(-1) if pos.side == "short" else Decimal(1)
        net += Decimal(pos.size_usd) * sign
    if not matched:
        return None
    side = "short" if net < 0 else "long"
    return abs(net), side


def _directional_exposure(delta: Decimal) -> str:
    abs_delta = abs(delta)
    if abs_delta >= _HIGH_DELTA:
        return "high"
    if abs_delta >= _ELEVATED_DELTA:
        return "elevated"
    return "low"


def _advisory_status(card: object) -> str | None:
    """Advisory earn lifecycle status for an alternative.

    Single source-of-truth: EarnAdvisoryStatus (no duplicated status strings). Mock-safe /
    fail-closed: a well-formed alternative surfaces NORMAL (legacy product operating-normally
    advisory state); returns None (never a fake value) when the card lacks the fields to
    assert a status. Advisory only — not a position, balance, or execution signal.
    """
    asset = getattr(card, "asset", None)
    apy = getattr(card, "apy_pct", None)
    if not asset or apy is None:
        return None
    return EarnAdvisoryStatus.NORMAL.value


class DseAnalyticsEnrichmentService:
    """Internal composition of the sandbox Risk/Earn services for DSE reasoning."""

    def __init__(
        self,
        *,
        greeks_provider: RiskGreeksProvider | None = None,
        earn_catalog: EarnRatesCatalog | None = None,
    ) -> None:
        self._greeks = greeks_provider
        self._earn = earn_catalog

    async def _greeks_summary(self, request: RecommendRequest) -> GreeksSummary | None:
        if self._greeks is None:
            return None
        exposure = _net_exposure(request)
        if exposure is None:
            # Not enough portfolio context (no positions in the asset) — degrade.
            return None
        notional, side = exposure
        portfolio = Decimal(request.portfolio_value_usd)
        greeks = self._greeks.get_portfolio_greeks(request.asset, notional, side, portfolio)
        delta = Decimal(greeks.delta)
        exposure_band = _directional_exposure(delta)
        notes: list[str] = []
        if exposure_band == "high":
            notes.append(
                f"High directional exposure (delta {greeks.delta}) on {request.asset}; "
                "consider hedging or sizing down."
            )
        elif exposure_band == "elevated":
            notes.append(
                f"Elevated directional exposure (delta {greeks.delta}) on {request.asset}."
            )
        if Decimal(greeks.gamma) > 0 or Decimal(greeks.theta) < 0:
            notes.append(
                f"Convexity/decay present (gamma {greeks.gamma}, theta {greeks.theta}) — "
                "leveraged or time-sensitive ideas carry path risk."
            )
        return GreeksSummary(
            greeks=greeks,
            notional_usd=str(notional.quantize(Decimal("0.01"))),
            side=side,
            directional_exposure=exposure_band,
            notes=notes,
            source=SANDBOX_MOCK,
        )

    async def _earn_alternatives(self, request: RecommendRequest) -> list[EarnAlternative] | None:
        if self._earn is None:
            return None
        cards = await self._earn.list_rates(list(DEFAULT_BASKET))
        if not cards:
            return None
        # Highest yields first — informational comparison only.
        ordered = sorted(cards, key=lambda c: Decimal(c.apy_pct), reverse=True)
        return [
            EarnAlternative(
                asset=c.asset,
                protocol=c.protocol,
                apy_pct=c.apy_pct,
                lockup_days=c.lockup_days,
                risk_band=c.risk_band.value,
                source=c.source,
                advisory_status=_advisory_status(c),
            )
            for c in ordered
        ]

    async def context(self, request: RecommendRequest) -> AnalyticsContext | None:
        """Build the per-request analytics context (None if nothing to add)."""
        summary = await self._greeks_summary(request)
        alternatives = await self._earn_alternatives(request)
        if summary is None and not alternatives:
            return None
        return AnalyticsContext(
            greeks_summary=summary,
            earn_alternatives=alternatives,
            analytics_version=ANALYTICS_VERSION,
            source=SANDBOX_MOCK,
        )

    def enrich_recommendation(
        self,
        rec: Recommendation,
        context: AnalyticsContext | None,
    ) -> Recommendation:
        """Attach explainable, additive riskNotes / alternatives to a rec."""
        if context is None:
            return rec
        risk_notes: list[str] | None = None
        if context.greeks_summary is not None and context.greeks_summary.notes:
            summary = context.greeks_summary
            if rec.action.category.value in {"perp", "spot"}:
                # Surface portfolio exposure context next to a tradable idea.
                risk_notes = list(summary.notes)
        alternatives: list[EarnAlternative] | None = None
        if rec.action.type in _CAPITAL_PRESERVATION and context.earn_alternatives:
            # Informational: idle capital could instead earn sandbox yield.
            top = context.earn_alternatives[:3]
            alternatives = top
        if risk_notes is None and alternatives is None:
            return rec
        return rec.model_copy(update={"risk_notes": risk_notes, "alternatives": alternatives})
