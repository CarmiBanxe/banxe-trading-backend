"""DSE engine (T7.1/T7.2) — advisory-only, deterministic mock (no network, no keys).

``MockDseEngine`` ranks explainable recommendations from fixed candidate metrics:
utility per the resolved risk profile, Kelly / Half-Kelly sizing, and sentiment +
stress overlays sourced through injectable **provider seams** (T7.2). It NEVER
signs, executes, or holds keys (self-custodial). Real sentiment (MiroFish) /
stress (MicroFish CMS-VAE) / quote-driven ER are separate, env-gated sprints —
wired here only as provider/port seams (mock by default).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .kelly import half_kelly_fraction, kelly_fraction
from .models import (
    Action,
    ActionCategory,
    ActionType,
    ModelVersions,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
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
from .utility import RiskMetrics, utility_score

if TYPE_CHECKING:
    from banxe_trading_backend.config import Settings
    from banxe_trading_backend.ports import ExchangePort, MarketDataPort, QuotePort


@runtime_checkable
class DseEngine(Protocol):
    """Compute ranked, explainable recommendations (advisory-only)."""

    async def recommend(self, request: RecommendRequest) -> RecommendResponse: ...


# --- deterministic stub candidate set (asset-agnostic; mock data) ----------- #


def _m(er: str, vol: str, var99: str, dd: str, liq: str) -> RiskMetrics:
    return RiskMetrics(Decimal(er), Decimal(vol), Decimal(var99), Decimal(dd), Decimal(liq))


# (type, category, metrics, win_rate p, win/loss ratio b, beta, reason)
_CANDIDATES: list[tuple[ActionType, ActionCategory, RiskMetrics, str, str, str, str]] = [
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


def _pct(fraction: Decimal) -> str:
    return str((fraction * 100).quantize(Decimal("0.0001")))


def _score(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001")))


class MockDseEngine:
    """Deterministic advisory mock — no network, no keys, no execution."""

    def __init__(
        self,
        *,
        sentiment_provider: SentimentProvider | None = None,
        stress_provider: StressProvider | None = None,
        quote_port: QuotePort | None = None,
        market_data: MarketDataPort | None = None,
        exchange: ExchangePort | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        # Data-source seams (T7.2): sentiment + stress through providers (mock by
        # default). Port seams (future): quote_port → ER/slippage; market_data /
        # exchange → perps + risk models. Unused by the mock.
        self._sentiment: SentimentProvider = sentiment_provider or MockSentimentProvider()
        self._stress: StressProvider = stress_provider or MockStressProvider()
        self._quote_port = quote_port
        self._market_data = market_data
        self._exchange = exchange
        self._now = now or (lambda: datetime.now(UTC).isoformat())

    @classmethod
    def from_settings(cls, settings: Settings, *, quote: QuotePort | None = None) -> MockDseEngine:
        # Provider seams selected by env (mock by default; real providers gated).
        return cls(
            sentiment_provider=build_sentiment_provider(settings.dse_sentiment_provider),
            stress_provider=build_stress_provider(settings.dse_stress_provider),
            quote_port=quote,
        )

    async def recommend(self, request: RecommendRequest) -> RecommendResponse:
        weights = weights_for(request.risk_profile, request.custom_weights)
        sentiment = await self._sentiment.get_sentiment(request.asset)
        recs: list[tuple[Decimal, Recommendation]] = []
        for atype, category, metrics, p, b, beta, reason in _CANDIDATES:
            u = utility_score(metrics, weights)
            kelly = kelly_fraction(Decimal(p), Decimal(b))
            half = half_kelly_fraction(Decimal(p), Decimal(b))
            stress = (
                await self._stress.get_stress(request.asset, Decimal(beta))
                if request.include_stress_tests
                else None
            )
            rec = Recommendation(
                rank=0,  # assigned after sort
                action=Action(type=atype, category=category, asset=request.asset),
                utility_score=_score(u),
                expected_return_pct=_pct(metrics.expected_return),
                volatility_pct=_pct(metrics.volatility),
                var99_pct=_pct(metrics.var99),
                max_drawdown_pct=_pct(metrics.max_drawdown),
                liquidity_score=str(metrics.liquidity.quantize(Decimal("0.0001"))),
                kelly_size_pct=_pct(kelly),
                half_kelly_size_pct=_pct(half),
                sentiment=sentiment if request.include_sentiment else None,
                stress_tests=stress,
                reasons=reason,
            )
            recs.append((u, rec))

        # Rank by utility descending (stable for ties), assign 1-based rank.
        recs.sort(key=lambda item: item[0], reverse=True)
        ranked = [rec.model_copy(update={"rank": i + 1}) for i, (_, rec) in enumerate(recs)]

        return RecommendResponse(
            recommendations=ranked,
            sentiment=sentiment,
            model_versions=_MODEL_VERSIONS,
            disclaimer=_DISCLAIMER,
            as_of=self._now(),
        )
