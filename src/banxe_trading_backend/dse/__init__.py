"""Decision Support Engine (DSE) — advisory-only (ADR-084, T7.1).

Explainable recommendations (utility + Kelly/Half-Kelly + mock sentiment/stress).
No auto-execution, no signing, no key custody, no gamification.
"""

from .engine import DseEngine, MockDseEngine
from .models import (
    Action,
    ActionCategory,
    ActionType,
    EarnMetrics,
    Greeks,
    ModelVersions,
    Position,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
    RiskMetrics,
    RiskProfile,
    SentimentScore,
    StressScenario,
    StressTests,
    UtilityWeights,
)
from .profiles import AGGRESSIVE, BALANCED, CONSERVATIVE, weights_for
from .providers import (
    MockSentimentProvider,
    MockStressProvider,
    SentimentProvider,
    StressProvider,
    build_sentiment_provider,
    build_stress_provider,
)

__all__ = [
    "DseEngine",
    "MockDseEngine",
    "ActionType",
    "ActionCategory",
    "RiskProfile",
    "UtilityWeights",
    "Action",
    "Position",
    "SentimentScore",
    "StressScenario",
    "StressTests",
    "Recommendation",
    "ModelVersions",
    "Greeks",
    "RiskMetrics",
    "EarnMetrics",
    "RecommendRequest",
    "RecommendResponse",
    "CONSERVATIVE",
    "BALANCED",
    "AGGRESSIVE",
    "weights_for",
    "SentimentProvider",
    "StressProvider",
    "MockSentimentProvider",
    "MockStressProvider",
    "build_sentiment_provider",
    "build_stress_provider",
]
