"""DSE engine (T7.1/T7.2) — advisory-only, deterministic mock (no network, no keys).

``MockDseEngine`` ranks explainable recommendations from fixed candidate metrics:
utility per the resolved risk profile, Kelly / Half-Kelly sizing, and sentiment +
stress overlays sourced through injectable **provider seams** (T7.2). It NEVER
signs, executes, or holds keys (self-custodial). Real sentiment (MiroFish) /
stress (MicroFish CMS-VAE) / quote-driven ER are separate, env-gated sprints —
wired here only as provider/port seams (mock by default).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from banxe_trading_backend.earn import (
    EarnRatesProvider,
    build_earn_provider,
    build_earn_rates_catalog,
)
from banxe_trading_backend.risk import (
    RiskMetricsProvider,
    build_risk_greeks_provider,
    build_risk_provider,
)
from banxe_trading_backend.services.dss_analytics_enrichment import (
    DseAnalyticsEnrichmentService,
)

from .kelly import half_kelly_fraction, kelly_fraction
from .models import (
    Action,
    ActionCategory,
    ActionType,
    AnalyticsContext,
    EarnMetrics,
    Greeks,
    ModelVersions,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
    RiskMetrics,
    UtilityComponent,
)
from .profiles import weights_for
from .providers import (
    MockSentimentProvider,
    MockStressProvider,
    SentimentProvider,
    StressProvider,
    build_sentiment_provider,
    build_stress_provider,
)
from .utility import CandidateMetrics, UtilityTerm, utility_components, utility_score

if TYPE_CHECKING:
    from banxe_trading_backend.config import Settings
    from banxe_trading_backend.ports import ExchangePort, MarketDataPort, QuotePort


@runtime_checkable
class DseEngine(Protocol):
    """Compute ranked, explainable recommendations (advisory-only)."""

    async def recommend(self, request: RecommendRequest) -> RecommendResponse: ...


# --- deterministic stub candidate set (asset-agnostic; mock data) ----------- #


def _m(er: str, vol: str, var99: str, dd: str, liq: str) -> CandidateMetrics:
    return CandidateMetrics(Decimal(er), Decimal(vol), Decimal(var99), Decimal(dd), Decimal(liq))


# (type, category, metrics, win_rate p, win/loss ratio b, beta, reason)
_CANDIDATES: list[tuple[ActionType, ActionCategory, CandidateMetrics, str, str, str, str]] = [
    (ActionType.OPEN_LONG, ActionCategory.PERP, _m("0.08", "0.04", "0.06", "0.05", "0.90"),
     "0.55", "1.5", "1.0", "Positive expected return with leverage; sized via Half-Kelly."),
    (ActionType.BUY, ActionCategory.SPOT, _m("0.06", "0.03", "0.04", "0.04", "0.95"),
     "0.58", "1.2", "1.0", "Spot accumulation; high liquidity, lower tail risk."),
    (ActionType.STAKE, ActionCategory.EARN, _m("0.05", "0.01", "0.015", "0.01", "0.60"),
     "0.90", "0.30", "0.2", "Yield with low volatility; lower liquidity."),
    (ActionType.HEDGE, ActionCategory.RISK, _m("0.01", "0.005", "0.01", "0.005", "0.80"),
     "0.50", "1.0", "-1.0", "Downside protection; small carrying cost."),
    (ActionType.HOLD, ActionCategory.META, _m("0", "0", "0", "0", "1.0"),
     "0.50", "1.0", "1.0", "Maintain current exposure; take no new risk."),
    (ActionType.WAIT, ActionCategory.META, _m("0", "0", "0", "0", "1.0"),
     "0.50", "1.0", "0.0", "Defer action pending a clearer signal."),
]

_DISCLAIMER = (
    "Advisory only — not investment advice and not an execution or "
    "portfolio-management service. BANXE DSE provides explainable model "
    "estimates (mock data in this build); you retain custody and sign all "
    "transactions yourself. Per MiCA / MiFID II this is decision-support output."
)
_MODEL_VERSIONS = ModelVersions(
    pricing="mock-pricing-0.1.0",
    sentiment="mock-sentiment-0.1.0",
    kelly="kelly-0.1.0",
    stress="mock-stress-0.1.0",
)
# T7.7 explainability-layer version (traceability of the breakdown surface).
_EXPLANATION_VERSION = "dss-explain-0.1.0"


def _pct(fraction: Decimal) -> str:
    return str((fraction * 100).quantize(Decimal("0.0001")))


def _score(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001")))


def _trace_id(request: RecommendRequest) -> str:
    """Deterministic trace id — same request canon → same id (traceability)."""
    positions = ";".join(
        f"{p.asset}:{p.size_usd}:{p.side}" for p in request.current_positions
    )
    custom = ""
    if request.custom_weights is not None:
        w = request.custom_weights
        custom = (
            f"{w.w1_expected_return},{w.w2_volatility},{w.w3_var99},"
            f"{w.w4_drawdown},{w.w5_liquidity}"
        )
    canon = (
        f"{request.asset}|{request.portfolio_value_usd}|{request.risk_profile.value}|"
        f"{positions}|{custom}|{request.include_stress_tests}|{request.include_sentiment}"
    )
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
    return f"dss-{digest}"


def _breakdown(terms: list[UtilityTerm]) -> tuple[list[UtilityComponent], str]:
    """Map utility terms to wire components + the single largest |contribution|."""
    components = [
        UtilityComponent(
            factor=t.factor,
            value=_score(t.value),
            weight=str(t.weight),
            contribution=_score(t.contribution),
            direction=t.direction,
        )
        for t in terms
    ]
    top = max(terms, key=lambda t: abs(t.contribution))
    return components, top.factor


def _fallback_risk_metrics(metrics: CandidateMetrics) -> RiskMetrics:
    """Degrade gracefully when no risk provider is configured (candidate-derived)."""
    return RiskMetrics(
        greeks=Greeks(delta="0", gamma="0", vega="0", theta="0", rho="0"),
        var99_pct=_pct(metrics.var99),
        dd_pct=_pct(metrics.max_drawdown),
        unrealized_pnl_pct="0.0000",
        unrealized_pnl_usd="0.00",
        liquidity_score=str(metrics.liquidity.quantize(Decimal("0.0001"))),
    )


def _effective_metrics(
    metrics: CandidateMetrics, risk: RiskMetrics, earn: EarnMetrics | None
) -> CandidateMetrics:
    """Fold available risk/earn metrics into the utility inputs (graceful)."""
    expected_return = metrics.expected_return
    if earn is not None:
        # Earn yield adds to the action's expected return.
        expected_return = expected_return + Decimal(earn.current_yield_pct) / 100
    # Use the (parametric) VaR99 from the risk layer.
    var99 = Decimal(risk.var99_pct) / 100
    return CandidateMetrics(
        expected_return=expected_return,
        volatility=metrics.volatility,
        var99=var99,
        max_drawdown=metrics.max_drawdown,
        liquidity=metrics.liquidity,
    )


class MockDseEngine:
    """Deterministic advisory mock — no network, no keys, no execution."""

    def __init__(
        self,
        *,
        sentiment_provider: SentimentProvider | None = None,
        stress_provider: StressProvider | None = None,
        risk_provider: RiskMetricsProvider | None = None,
        earn_provider: EarnRatesProvider | None = None,
        enrichment: DseAnalyticsEnrichmentService | None = None,
        quote_port: QuotePort | None = None,
        market_data: MarketDataPort | None = None,
        exchange: ExchangePort | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        # Data-source seams: sentiment + stress (T7.2), risk + earn (T7.3) through
        # providers (mock by default). Pass None to degrade gracefully. Port seams
        # (future): quote_port → ER/slippage; market_data/exchange → perps/risk.
        self._sentiment: SentimentProvider = sentiment_provider or MockSentimentProvider()
        self._stress: StressProvider = stress_provider or MockStressProvider()
        self._risk = risk_provider
        self._earn = earn_provider
        # T7.6 internal analytics enrichment (sandbox-mock; explanation-only).
        self._enrichment = enrichment
        self._quote_port = quote_port
        self._market_data = market_data
        self._exchange = exchange
        self._now = now or (lambda: datetime.now(UTC).isoformat())

    @classmethod
    def from_settings(cls, settings: Settings, *, quote: QuotePort | None = None) -> MockDseEngine:
        # Provider seams selected by env (mock by default; real providers gated).
        # T7.6: internal-only enrichment composes the T7.5 sandbox Risk Greeks +
        # Earn rates services in-process (no HTTP self-calls, mock default).
        enrichment = DseAnalyticsEnrichmentService(
            greeks_provider=build_risk_greeks_provider(settings.risk_greeks_provider),
            earn_catalog=build_earn_rates_catalog(
                settings.earn_rates_provider,
                build_earn_provider(settings.dse_earn_provider),
            ),
        )
        return cls(
            sentiment_provider=build_sentiment_provider(settings.dse_sentiment_provider),
            stress_provider=build_stress_provider(settings.dse_stress_provider),
            risk_provider=build_risk_provider(settings.dse_risk_provider),
            earn_provider=build_earn_provider(settings.dse_earn_provider),
            enrichment=enrichment,
            quote_port=quote,
        )

    async def recommend(self, request: RecommendRequest) -> RecommendResponse:
        weights = weights_for(request.risk_profile, request.custom_weights)
        sentiment = await self._sentiment.get_sentiment(request.asset)
        recs: list[tuple[Decimal, Recommendation]] = []
        for atype, category, metrics, p, b, beta, reason in _CANDIDATES:
            action = Action(type=atype, category=category, asset=request.asset)
            # Risk metrics: provider when configured, else candidate-derived fallback.
            risk = (
                await self._risk.get_risk_metrics(request, action, metrics)
                if self._risk is not None
                else _fallback_risk_metrics(metrics)
            )
            # Earn metrics only for earn-category actions, when a provider is set.
            earn: EarnMetrics | None = None
            if category is ActionCategory.EARN and self._earn is not None:
                earn = await self._earn.get_earn_metrics(request.asset)

            effective = _effective_metrics(metrics, risk, earn)
            u = utility_score(effective, weights)
            # T7.7 explainability: decompose the SAME (effective metrics, weights)
            # that produced `u` — contributions sum to utility_score (no re-rank).
            components, top_driver = _breakdown(utility_components(effective, weights))
            kelly = kelly_fraction(Decimal(p), Decimal(b))
            half = half_kelly_fraction(Decimal(p), Decimal(b))
            stress = (
                await self._stress.get_stress(request.asset, Decimal(beta))
                if request.include_stress_tests
                else None
            )
            reasons = f"{reason} VaR99 {risk.var99_pct}%, delta {risk.greeks.delta}."
            if earn is not None:
                reasons += f" Yield {earn.current_yield_pct}% ({earn.protocol}, {earn.chain})."

            rec = Recommendation(
                rank=0,  # assigned after sort
                action=action,
                utility_score=_score(u),
                expected_return_pct=_pct(metrics.expected_return),
                volatility_pct=_pct(metrics.volatility),
                var99_pct=risk.var99_pct,
                max_drawdown_pct=_pct(metrics.max_drawdown),
                liquidity_score=str(metrics.liquidity.quantize(Decimal("0.0001"))),
                kelly_size_pct=_pct(kelly),
                half_kelly_size_pct=_pct(half),
                risk_metrics=risk,
                earn_metrics=earn,
                sentiment=sentiment if request.include_sentiment else None,
                stress_tests=stress,
                reasons=reasons,
                utility_breakdown=components,
                top_driver=top_driver,
            )
            recs.append((u, rec))

        # Rank by utility descending (stable for ties), assign 1-based rank.
        # NOTE (T7.6): enrichment is explanation-only — it does NOT re-rank; the
        # established utility framework drives ordering unchanged.
        recs.sort(key=lambda item: item[0], reverse=True)
        ranked = [rec.model_copy(update={"rank": i + 1}) for i, (_, rec) in enumerate(recs)]

        # T7.6: additive internal analytics enrichment (sandbox-mock). Graceful —
        # absent when there is no enrichment service or no portfolio context.
        analytics: AnalyticsContext | None = None
        if self._enrichment is not None:
            analytics = await self._enrichment.context(request)
            if analytics is not None:
                ranked = [self._enrichment.enrich_recommendation(rec, analytics) for rec in ranked]

        return RecommendResponse(
            recommendations=ranked,
            sentiment=sentiment,
            model_versions=_MODEL_VERSIONS,
            disclaimer=_DISCLAIMER,
            analytics_context=analytics,
            trace_id=_trace_id(request),
            explanation_version=_EXPLANATION_VERSION,
            as_of=self._now(),
        )
