"""DSE pydantic models — strictly mirror docs/specs/dse-*.yaml (T7.1).

Advisory-only domain. All monetary / metric fields are decimal strings (I-01).
Field aliases are camelCase (CamelModel) to match the OpenAPI schemas; a
conformance test asserts model ↔ spec parity.
"""

from __future__ import annotations

from enum import Enum

from banxe_trading_backend.models import CamelModel, DecimalStr


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
    sentiment: SentimentScore | None = None
    stress_tests: StressTests | None = None
    reasons: str


class ModelVersions(CamelModel):
    pricing: str
    sentiment: str
    kelly: str
    stress: str


class RecommendRequest(CamelModel):
    asset: str
    portfolio_value_usd: DecimalStr
    current_positions: list[Position] = []
    risk_profile: RiskProfile = RiskProfile.BALANCED
    custom_weights: UtilityWeights | None = None
    include_stress_tests: bool = True
    include_sentiment: bool = True


class RecommendResponse(CamelModel):
    recommendations: list[Recommendation]
    sentiment: SentimentScore
    model_versions: ModelVersions
    disclaimer: str
    as_of: str
