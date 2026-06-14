"""DSE engine (T7.1) — advisory-only, deterministic mock (no network, no keys).

``MockDseEngine`` produces ranked, explainable recommendations from fixed,
representative stub metrics: utility per the resolved risk profile, Kelly /
Half-Kelly sizing, and mock sentiment + stress overlays. It NEVER signs, executes,
or holds keys (self-custodial). Real sentiment (MiroFish) / stress (MicroFish
CMS-VAE) / quote-driven ER are separate, env-gated sprints — wired here only as
optional injected port seams (unused in the mock).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .models import (
    Action,
    ActionCategory,
    ActionType,
    ModelVersions,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
    SentimentScore,
    StressScenario,
    StressTests,
)
from .profiles import weights_for
from .utility import RiskMetrics, utility_score

if TYPE_CHECKING:
    from banxe_trading_backend.ports import ExchangePort, MarketDataPort, QuotePort

from .kelly import half_kelly_fraction, kelly_fraction


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

# Fixed stress shocks (price moves). Mock/fixture this sprint.
_SHOCKS: list[tuple[str, str]] = [
    ("base", "0"),
    ("shockDown", "-0.20"),
    ("shockUp", "0.20"),
    ("blackSwan", "-0.50"),
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


def _mock_sentiment() -> SentimentScore:
    return SentimentScore(
        score="0.35", news="0.40", onchain="0.30", social="0.35",
        model_version=_MODEL_VERSIONS.sentiment,
    )


def _mock_stress(beta: Decimal) -> StressTests:
    scenarios: dict[str, StressScenario] = {}
    for name, shock in _SHOCKS:
        pnl = Decimal(shock) * beta
        scenarios[name] = StressScenario(
            name=name,
            pnl_pct=_pct(pnl),
            explanation=f"Price move {shock} × action beta {beta} → P&L {_pct(pnl)}%.",
        )
    return StressTests(
        base=scenarios["base"],
        shock_down=scenarios["shockDown"],
        shock_up=scenarios["shockUp"],
        black_swan=scenarios["blackSwan"],
        explanation="Deterministic mock stress scenarios (MicroFish CMS-VAE is a later sprint).",
    )


class MockDseEngine:
    """Deterministic advisory mock — no network, no keys, no execution."""

    def __init__(
        self,
        *,
        quote_port: QuotePort | None = None,
        market_data: MarketDataPort | None = None,
        exchange: ExchangePort | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        # Integration seams (future): quote_port → ER/slippage from QuotePort;
        # market_data/exchange → perps + risk models. Unused by the mock.
        self._quote_port = quote_port
        self._market_data = market_data
        self._exchange = exchange
        self._now = now or (lambda: datetime.now(UTC).isoformat())

    async def recommend(self, request: RecommendRequest) -> RecommendResponse:
        weights = weights_for(request.risk_profile, request.custom_weights)
        recs: list[tuple[Decimal, Recommendation]] = []
        for atype, category, metrics, p, b, beta, reason in _CANDIDATES:
            u = utility_score(metrics, weights)
            kelly = kelly_fraction(Decimal(p), Decimal(b))
            half = half_kelly_fraction(Decimal(p), Decimal(b))
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
                sentiment=_mock_sentiment() if request.include_sentiment else None,
                stress_tests=_mock_stress(Decimal(beta)) if request.include_stress_tests else None,
                reasons=reason,
            )
            recs.append((u, rec))

        # Rank by utility descending (stable for ties), assign 1-based rank.
        recs.sort(key=lambda item: item[0], reverse=True)
        ranked = [rec.model_copy(update={"rank": i + 1}) for i, (_, rec) in enumerate(recs)]

        return RecommendResponse(
            recommendations=ranked,
            sentiment=_mock_sentiment(),
            model_versions=_MODEL_VERSIONS,
            disclaimer=_DISCLAIMER,
            as_of=self._now(),
        )
