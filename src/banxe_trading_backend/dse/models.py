"""DSE pydantic models — strictly mirror docs/specs/dse-*.yaml (T7.1).

Advisory-only domain. All monetary / metric fields are decimal strings (I-01).
Field aliases are camelCase (CamelModel) to match the OpenAPI schemas; a
conformance test asserts model ↔ spec parity.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import Field, field_validator

from banxe_trading_backend.models import CamelModel, DecimalStr

#: Bounded, charset-safe partner identifier (no secrets/PII; opaque, advisory).
PartnerRef = Annotated[str, Field(max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")]


class ActionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    SWAP = "SWAP"
    OPEN_LONG = "OPEN_LONG"
    OPEN_SHORT = "OPEN_SHORT"
    CLOSE = "CLOSE"
    ADJUST_SL = "ADJUST_SL"
    STAKE = "STAKE"
    REBALANCE = "REBALANCE"
    HEDGE = "HEDGE"
    HOLD = "HOLD"
    WAIT = "WAIT"


class ActionCategory(str, Enum):
    SPOT = "spot"
    PERP = "perp"
    EARN = "earn"
    RISK = "risk"
    META = "meta"


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


class UtilityWeights(CamelModel):
    w1_expected_return: DecimalStr
    w2_volatility: DecimalStr
    w3_var99: DecimalStr
    w4_drawdown: DecimalStr
    w5_liquidity: DecimalStr


class Action(CamelModel):
    type: ActionType
    category: ActionCategory
    asset: str
    description: str | None = None


class SentimentScore(CamelModel):
    score: DecimalStr  # S in [-1, 1]
    news: DecimalStr
    onchain: DecimalStr
    social: DecimalStr
    model_version: str


class StressScenario(CamelModel):
    name: str
    pnl_pct: DecimalStr
    explanation: str


class StressTests(CamelModel):
    base: StressScenario
    shock_down: StressScenario
    shock_up: StressScenario
    black_swan: StressScenario
    explanation: str


class Position(CamelModel):
    asset: str
    size_usd: DecimalStr
    side: str  # long | short | spot


class Greeks(CamelModel):
    """Aggregated option/portfolio Greeks (decimal strings, I-01). Advisory."""

    delta: DecimalStr
    gamma: DecimalStr
    vega: DecimalStr
    theta: DecimalStr
    rho: DecimalStr


class RiskMetrics(CamelModel):
    """Risk advisory metrics for a recommendation (estimates, not guarantees)."""

    greeks: Greeks
    var99_pct: DecimalStr
    dd_pct: DecimalStr
    unrealized_pnl_pct: DecimalStr
    unrealized_pnl_usd: DecimalStr
    liquidity_score: DecimalStr


class EarnMetrics(CamelModel):
    """Earn advisory metrics for earn-category actions (yields are estimates)."""

    current_yield_pct: DecimalStr
    protocol: str
    chain: str
    lockup_days: int
    variable_rate: bool
    risk_summary: str


class EarnAlternative(CamelModel):
    """An informational sandbox earn alternative surfaced in DSE reasoning (T7.6).

    Derived from the internal sandbox Earn rates catalogue — yields are estimates
    / simulations, NOT a promise of return and NOT an execution offer.
    """

    asset: str
    protocol: str
    apy_pct: DecimalStr
    lockup_days: int
    risk_band: str
    source: str
    # M1.5 additive: advisory lifecycle (EarnAdvisoryStatus SoT); None if not determinable
    advisory_status: str | None = None


class GreeksSummary(CamelModel):
    """Portfolio-level Greeks summary used as an advisory enrichment (T7.6)."""

    greeks: Greeks
    notional_usd: DecimalStr
    side: str
    directional_exposure: str  # qualitative: low | elevated | high
    notes: list[str]
    source: str


class AnalyticsContext(CamelModel):
    """Optional, additive DSE analytics enrichment (T7.6, sandbox-mock).

    Internal-only composition of the T7.5 Risk Greeks / Earn rates sandbox
    services. Informational explanation context — it does NOT add execution and
    does NOT change the public endpoint surface.
    """

    greeks_summary: GreeksSummary | None = None
    earn_alternatives: list[EarnAlternative] | None = None
    analytics_version: str
    source: str


class UtilityComponent(CamelModel):
    """One signed term of the utility decomposition (explainability, T7.7).

    Exposes the EXISTING utility math per factor; the contributions sum to the
    recommendation's ``utilityScore``. It does not change utility or ranking.
    """

    factor: str  # expectedReturn | volatility | var99 | drawdown | liquidity
    value: DecimalStr
    weight: DecimalStr
    contribution: DecimalStr
    direction: str  # positive | negative


class Recommendation(CamelModel):
    rank: int
    action: Action
    utility_score: DecimalStr
    expected_return_pct: DecimalStr
    volatility_pct: DecimalStr
    var99_pct: DecimalStr
    max_drawdown_pct: DecimalStr
    liquidity_score: DecimalStr
    kelly_size_pct: DecimalStr
    half_kelly_size_pct: DecimalStr
    risk_metrics: RiskMetrics
    earn_metrics: EarnMetrics | None = None
    sentiment: SentimentScore | None = None
    stress_tests: StressTests | None = None
    reasons: str
    # T7.6 additive enrichment (optional, sandbox-mock-derived; explanation-only).
    risk_notes: list[str] | None = None
    alternatives: list[EarnAlternative] | None = None
    # T7.7 additive explainability: signed decomposition of utilityScore +
    # the single largest driver. Exposes existing math; ranking is unchanged.
    utility_breakdown: list[UtilityComponent] | None = None
    top_driver: str | None = None


class ModelVersions(CamelModel):
    pricing: str
    sentiment: str
    kelly: str
    stress: str


class DecisionTraceStep(CamelModel):
    """Per-candidate trace of inputs → normalized features → score (T7.8 debug).

    Sandbox/dev observability only. Carries request-derived + mock-model values;
    NO secrets. Reconstructs how raw candidate metrics became the utility inputs.
    """

    rank: int
    action_type: str
    action_category: str
    raw_expected_return: DecimalStr
    earn_yield_pct: DecimalStr | None = None
    effective_expected_return: DecimalStr
    volatility: DecimalStr
    var99: DecimalStr
    var99_source: str  # risk-provider | candidate-fallback
    drawdown: DecimalStr
    liquidity: DecimalStr
    utility_score: DecimalStr


class DecisionTrace(CamelModel):
    """Opt-in sandbox decision-trace (T7.8) — keyed by traceId; dev-only.

    Double-gated (BANXE_DSE_DEBUG_ENABLED + X-Banxe-Dse-Debug header); absent in
    production. Lets an engineer reconstruct the full mock decision path. Contains
    NO production secrets/keys/endpoints — only request-derived data, mock model
    metadata, and provider class names. Does NOT change utility or ranking.
    """

    trace_id: str
    risk_profile: str
    weights: UtilityWeights
    risk_provider: str
    earn_provider: str
    sentiment_provider: str
    stress_provider: str
    enrichment_applied: bool
    steps: list[DecisionTraceStep]
    note: str


class PartnerContext(CamelModel):
    """Optional sandbox partner context (S11) — advisory, metering-READY only.

    Opaque, bounded, non-secret correlation context. It carries NO auth, NO
    billing, NO entitlement — only "sandbox" mode is supported (anything else
    fails closed). Provided on the request; echoed back safely.
    """

    partner_id: PartnerRef | None = None
    client_ref: PartnerRef | None = None
    mode: str = "sandbox"  # only "sandbox" supported; non-sandbox fails closed

    @field_validator("mode")
    @classmethod
    def _sandbox_only(cls, value: str) -> str:
        # Schema-layer fail-closed: reject any non-sandbox mode at request parse.
        if value != "sandbox":
            raise ValueError(
                f"partner mode {value!r} is OPERATOR DECISION REQUIRED "
                "(sandbox-only; no production partner mode is wired)"
            )
        return value


class ProductMetadata(CamelModel):
    """Partner/product-safe metadata block (S11) — additive, opt-in, NO secrets.

    Populated only when the request supplies ``partnerContext``. Surfaces safe
    provenance (tier class per domain), normalized model/version exposure, the
    explainability model, advisory/self-custodial flags, and a correlation id.
    """

    surface: str
    engine_mode: str
    advisory: bool
    executes: bool
    self_custodial: bool
    determinism: str
    provider_provenance: dict[str, str]
    model_versions: ModelVersions
    explanation_version: str
    explanation_model: str
    request_id: str
    partner: PartnerContext | None = None
    disclaimer: str


class RecommendRequest(CamelModel):
    asset: str
    portfolio_value_usd: DecimalStr
    current_positions: list[Position] = []
    risk_profile: RiskProfile = RiskProfile.BALANCED
    custom_weights: UtilityWeights | None = None
    include_stress_tests: bool = True
    include_sentiment: bool = True
    # S11 additive: optional sandbox partner context (advisory; opt-in).
    partner_context: PartnerContext | None = None


class RecommendResponse(CamelModel):
    recommendations: list[Recommendation]
    sentiment: SentimentScore
    model_versions: ModelVersions
    disclaimer: str
    # T7.6 additive enrichment (optional; absent/null when no portfolio context).
    analytics_context: AnalyticsContext | None = None
    # T7.7 additive traceability: deterministic id (same request -> same id) +
    # the explainability-layer version. Optional / backward-compatible.
    trace_id: str | None = None
    explanation_version: str | None = None
    # T7.8 opt-in sandbox decision-trace (dev-only, double-gated; null in prod).
    decision_trace: DecisionTrace | None = None
    # S11 additive: partner/product metadata (opt-in; null unless partnerContext).
    product: ProductMetadata | None = None
    as_of: str
