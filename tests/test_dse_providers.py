"""DSE provider seams (T7.2) — sentiment/stress pluggable, mock default, no network."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from banxe_trading_backend.config import Settings
from banxe_trading_backend.dse import (
    MockDseEngine,
    MockSentimentProvider,
    MockStressProvider,
    RecommendRequest,
    SentimentProvider,
    StressProvider,
    build_sentiment_provider,
    build_stress_provider,
)
from banxe_trading_backend.dse.models import (
    SentimentScore,
    StressScenario,
    StressTests,
)


def test_mock_providers_satisfy_protocols() -> None:
    assert isinstance(MockSentimentProvider(), SentimentProvider)
    assert isinstance(MockStressProvider(), StressProvider)


def test_selector_returns_mock_by_default() -> None:
    assert isinstance(build_sentiment_provider("mock"), MockSentimentProvider)
    assert isinstance(build_stress_provider("mock"), MockStressProvider)


def test_selector_rejects_unwired_provider() -> None:
    # Real providers (e.g. MiroFish/MicroFish) are operator-gated — not wired.
    with pytest.raises(ValueError, match="not wired"):
        build_sentiment_provider("mirofish")
    with pytest.raises(ValueError, match="not wired"):
        build_stress_provider("microfish")


def test_from_settings_uses_mock_providers() -> None:
    engine = MockDseEngine.from_settings(Settings())
    resp = asyncio.run(engine.recommend(RecommendRequest(asset="BTCUSDT", portfolio_value_usd="1")))
    assert resp.sentiment.score == "0.35"
    assert resp.recommendations[0].stress_tests is not None


def test_engine_uses_injected_providers() -> None:
    class FakeSentiment:
        async def get_sentiment(self, asset: str) -> SentimentScore:
            return SentimentScore(
                score="-0.50", news="-0.5", onchain="-0.5", social="-0.5", model_version="fake-1"
            )

    class FakeStress:
        async def get_stress(self, asset: str, beta: Decimal) -> StressTests:
            s = StressScenario(name="x", pnl_pct="1.0", explanation="fake")
            return StressTests(
                base=s, shock_down=s, shock_up=s, black_swan=s, explanation="fake stress"
            )

    engine = MockDseEngine(sentiment_provider=FakeSentiment(), stress_provider=FakeStress())
    resp = asyncio.run(engine.recommend(RecommendRequest(asset="ETHUSDT", portfolio_value_usd="1")))
    assert resp.sentiment.score == "-0.50"  # injected provider used
    assert resp.recommendations[0].stress_tests is not None
    assert resp.recommendations[0].stress_tests.explanation == "fake stress"


def test_from_settings_rejects_unwired_provider_env() -> None:
    with pytest.raises(ValueError, match="not wired"):
        MockDseEngine.from_settings(Settings(dse_sentiment_provider="mirofish"))
