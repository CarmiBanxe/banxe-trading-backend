"""DSE data-source seams (T7.2) — sentiment + stress providers, mock default.

Soft-integration prep: the engine reads sentiment and stress through Protocols,
so real providers (MiroFish sentiment / MicroFish CMS-VAE stress) can be added
later behind the same interfaces, env-gated. Only the deterministic mocks ship
now — NO network, NO keys, advisory-only (ADR-084). The provider is selected by
``BANXE_DSE_SENTIMENT_PROVIDER`` / ``BANXE_DSE_STRESS_PROVIDER`` (default "mock").
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from .models import SentimentScore, StressScenario, StressTests

_MOCK_SENTIMENT_VERSION = "mock-sentiment-0.1.0"
_MOCK_STRESS_SHOCKS: list[tuple[str, str]] = [
    ("base", "0"),
    ("shockDown", "-0.20"),
    ("shockUp", "0.20"),
    ("blackSwan", "-0.50"),
]


def _pct(value: Decimal) -> str:
    return str((value * 100).quantize(Decimal("0.0001")))


@runtime_checkable
class SentimentProvider(Protocol):
    """Aggregate market sentiment for an asset (S in [-1,1] + decomposition)."""

    async def get_sentiment(self, asset: str) -> SentimentScore: ...


@runtime_checkable
class StressProvider(Protocol):
    """Stress scenarios for an action's directional exposure (beta)."""

    async def get_stress(self, asset: str, beta: Decimal) -> StressTests: ...


class MockSentimentProvider:
    """Deterministic mock sentiment — no network. Real MiroFish is a later sprint."""

    async def get_sentiment(self, asset: str) -> SentimentScore:
        return SentimentScore(
            score="0.35",
            news="0.40",
            onchain="0.30",
            social="0.35",
            model_version=_MOCK_SENTIMENT_VERSION,
        )


class MockStressProvider:
    """Deterministic mock stress — no network. Real MicroFish CMS-VAE is a later sprint."""

    async def get_stress(self, asset: str, beta: Decimal) -> StressTests:
        scenarios: dict[str, StressScenario] = {}
        for name, shock in _MOCK_STRESS_SHOCKS:
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
            explanation=(
                "Deterministic mock stress scenarios (MicroFish CMS-VAE is a later sprint)."
            ),
        )


def build_sentiment_provider(name: str) -> SentimentProvider:
    """Resolve a sentiment provider by name. Only 'mock' is wired (default)."""
    if name == "mock":
        return MockSentimentProvider()
    # Real providers (e.g. MiroFish) are OPERATOR-GATED future sprints — keys/network.
    raise ValueError(
        f"sentiment provider {name!r} is not wired (operator-gated); only 'mock' is available"
    )


def build_stress_provider(name: str) -> StressProvider:
    """Resolve a stress provider by name. Only 'mock' is wired (default)."""
    if name == "mock":
        return MockStressProvider()
    raise ValueError(
        f"stress provider {name!r} is not wired (operator-gated); only 'mock' is available"
    )
