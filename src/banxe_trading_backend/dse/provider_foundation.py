"""DSE provider foundation (Sprint S10) — reversible provider abstractions.

Formalizes the DSE data-source providers behind explicit interfaces with a
per-domain tier matrix (MOCK / STUB / LIVE_READY) and **fail-closed** resolution.
The runtime default everywhere stays **mock**, CI-safe, with NO network and NO
credentials. ``LIVE_READY`` is a CI-safe scaffold: it is selectable and
constructible but **inert** — it performs no network and needs no real keys.
Actual live activation (real network/credentials) is OPERATOR-GATED (ODR) and is
NOT wired here; requesting it without the master switch + credentials fails closed.

This layer changes NO utility and NO ranking: the mock and live-ready tiers return
the established deterministic values, so ``POST /v1/dss/recommend`` is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .models import SentimentScore, StressScenario, StressTests
from .provider_layer import LiveProviderNotWiredError
from .providers import (
    MockSentimentProvider,
    MockStressProvider,
    SentimentProvider,
    StressProvider,
)

if TYPE_CHECKING:
    from banxe_trading_backend.config import Settings

#: Domains the foundation resolves through explicit provider abstractions.
FOUNDATION_DOMAINS = ("market", "sentiment", "stress")


class ProviderTier(str, Enum):
    """Per-domain provider tier. Only mock + stub run live data through; live-ready
    is a CI-safe inert scaffold (no network/credentials). Real activation is ODR."""

    MOCK = "mock"
    STUB = "stub"
    LIVE_READY = "live-ready"


# --------------------------- market data provider --------------------------- #


@dataclass(frozen=True)
class MarketSnapshot:
    """Market data input used by the DSE (deterministic decimal strings, I-01)."""

    asset: str
    price: str
    volatility: str
    liquidity: str
    source: str


@runtime_checkable
class MarketDataProvider(Protocol):
    async def get_market(self, asset: str) -> MarketSnapshot: ...


class MockMarketDataProvider:
    """Deterministic mock market snapshot — no network."""

    async def get_market(self, asset: str) -> MarketSnapshot:
        return MarketSnapshot(asset.upper(), "67251.00", "0.0400", "0.9000", "mock-market-0.1.0")


class StubMarketDataProvider:
    """Minimal neutral stub — for contract/fallback tests (no network)."""

    async def get_market(self, asset: str) -> MarketSnapshot:
        return MarketSnapshot(asset.upper(), "0", "0", "0", "stub-market-0.1.0")


class LiveReadyMarketDataProvider:
    """Live-ready scaffold — CI-safe & INERT (no network, no creds). Activation=ODR."""

    def __init__(self) -> None:
        self._inner = MockMarketDataProvider()

    async def get_market(self, asset: str) -> MarketSnapshot:
        snap = await self._inner.get_market(asset)
        return MarketSnapshot(snap.asset, snap.price, snap.volatility, snap.liquidity,
                              "live-ready-inert")


# --------------------------- sentiment / stress ----------------------------- #


class StubSentimentProvider:
    async def get_sentiment(self, asset: str) -> SentimentScore:
        return SentimentScore(
            score="0", news="0", onchain="0", social="0", model_version="stub-sentiment-0.1.0"
        )


class LiveReadySentimentProvider:
    """Live-ready scaffold — CI-safe & inert (delegates to mock). Activation=ODR."""

    def __init__(self) -> None:
        self._inner = MockSentimentProvider()

    async def get_sentiment(self, asset: str) -> SentimentScore:
        return await self._inner.get_sentiment(asset)


class StubStressProvider:
    async def get_stress(self, asset: str, beta: Decimal) -> StressTests:
        zero = StressScenario(name="base", pnl_pct="0.0000", explanation="stub: no shock")
        return StressTests(
            base=zero,
            shock_down=StressScenario(name="shockDown", pnl_pct="0.0000", explanation="stub"),
            shock_up=StressScenario(name="shockUp", pnl_pct="0.0000", explanation="stub"),
            black_swan=StressScenario(name="blackSwan", pnl_pct="0.0000", explanation="stub"),
            explanation="Stub stress scenarios (neutral; for contract/fallback tests).",
        )


class LiveReadyStressProvider:
    """Live-ready scaffold — CI-safe & inert (delegates to mock). Activation=ODR."""

    def __init__(self) -> None:
        self._inner = MockStressProvider()

    async def get_stress(self, asset: str, beta: Decimal) -> StressTests:
        return await self._inner.get_stress(asset, beta)


# ------------------------------ resolution ---------------------------------- #


@dataclass(frozen=True)
class FoundationProviders:
    """Resolved per-domain providers + their tiers (mock by default)."""

    market: MarketDataProvider
    sentiment: SentimentProvider
    stress: StressProvider
    market_tier: str
    sentiment_tier: str
    stress_tier: str


_MARKET: dict[ProviderTier, Callable[[], MarketDataProvider]] = {
    ProviderTier.MOCK: MockMarketDataProvider,
    ProviderTier.STUB: StubMarketDataProvider,
    ProviderTier.LIVE_READY: LiveReadyMarketDataProvider,
}
_SENTIMENT: dict[ProviderTier, Callable[[], SentimentProvider]] = {
    ProviderTier.MOCK: MockSentimentProvider,
    ProviderTier.STUB: StubSentimentProvider,
    ProviderTier.LIVE_READY: LiveReadySentimentProvider,
}
_STRESS: dict[ProviderTier, Callable[[], StressProvider]] = {
    ProviderTier.MOCK: MockStressProvider,
    ProviderTier.STUB: StubStressProvider,
    ProviderTier.LIVE_READY: LiveReadyStressProvider,
}


def resolve_tier(value: str) -> ProviderTier:
    """Parse a tier string (fail closed on unknown values)."""
    try:
        return ProviderTier(value)
    except ValueError as exc:
        valid = ", ".join(t.value for t in ProviderTier)
        raise LiveProviderNotWiredError(
            f"unknown DSE provider tier {value!r}; valid: {valid}"
        ) from exc


def _guard_live_ready(domain: str, settings: Settings) -> None:
    """Fail-closed validation for a LIVE_READY tier.

    When the master switch is off (default), LIVE_READY runs INERT (CI-safe). When
    the switch is on, we refuse: credentials missing → fail closed; credentials
    present → still fail closed because no live network adapter is wired (ODR).
    """
    if not settings.dse_live_allowed:
        return  # inert scaffold; no network, no creds, CI-safe
    api_key = str(getattr(settings, f"dse_{domain}_api_key", ""))
    base_url = str(getattr(settings, f"dse_{domain}_base_url", ""))
    if not api_key or not base_url:
        raise LiveProviderNotWiredError(
            f"{domain} LIVE_READY with BANXE_DSE_LIVE_ALLOWED set but credentials "
            "missing — failing closed (OPERATOR DECISION REQUIRED)"
        )
    raise LiveProviderNotWiredError(
        f"{domain} live network adapter is not wired (ODR); cannot activate this sprint"
    )


def resolve_foundation(settings: Settings) -> FoundationProviders:
    """Resolve the per-domain providers from settings (mock default, fail-closed)."""
    tiers = {
        "market": resolve_tier(settings.dse_market_tier),
        "sentiment": resolve_tier(settings.dse_sentiment_tier),
        "stress": resolve_tier(settings.dse_stress_tier),
    }
    for domain, tier in tiers.items():
        if tier is ProviderTier.LIVE_READY:
            _guard_live_ready(domain, settings)
    return FoundationProviders(
        market=_MARKET[tiers["market"]](),
        sentiment=_SENTIMENT[tiers["sentiment"]](),
        stress=_STRESS[tiers["stress"]](),
        market_tier=tiers["market"].value,
        sentiment_tier=tiers["sentiment"].value,
        stress_tier=tiers["stress"].value,
    )


def foundation_profile(foundation: FoundationProviders) -> dict[str, dict[str, str]]:
    """Safe, NON-secret provenance descriptor (domain → tier + source class name)."""
    return {
        "market": {"tier": foundation.market_tier, "source": type(foundation.market).__name__},
        "sentiment": {
            "tier": foundation.sentiment_tier,
            "source": type(foundation.sentiment).__name__,
        },
        "stress": {"tier": foundation.stress_tier, "source": type(foundation.stress).__name__},
    }


# --------------------------- S6.2-EN market-data route ---------------------- #


#: Provider value selecting the public dYdX v4 Indexer for market data.
DYDX_MARKET_PROVIDER = "dydx"


def resolve_market_data_route(settings: Settings) -> str:
    """S6.2-EN: pick the MarketDataPort route from the DSE flag triple.

    Returns ``"dydx"`` iff **all three** of the gating flags are on:
    ``BANXE_DSE_PROVIDER_MODE=sandbox-live`` **and**
    ``BANXE_DSE_MARKET_PROVIDER=dydx`` **and**
    ``BANXE_DSE_LIVE_ALLOWED=true``. Any other combination — kill-switch off,
    non-dydx provider, mock mode — returns ``"mock"`` (fail-closed; the spec
    forbids hard-failing on a partial config). The dYdX Indexer is the only
    wired live market source this sprint; nothing else is registered here.
    """
    if (
        settings.dse_provider_mode == "sandbox-live"
        and settings.dse_market_provider == DYDX_MARKET_PROVIDER
        and settings.dse_live_allowed
    ):
        return DYDX_MARKET_PROVIDER
    return "mock"


# --------------------------- S6.4-EN exchange route ------------------------- #


#: Provider value selecting the dYdX ExchangePort adapter (UNSIGNED intent).
DYDX_EXCHANGE_PROVIDER = "dydx"


def resolve_exchange_route(settings: Settings) -> str:
    """S6.4-EN Phase-2a: pick the ExchangePort route from the FULL combo.

    Returns ``"dydx"`` iff **all five** of the gating conditions hold:
      * ``BANXE_EXCHANGE_PROVIDER=dydx``                     (provider selection)
      * ``BANXE_DSE_PROVIDER_MODE=sandbox-live``             (overall mode)
      * ``BANXE_DSE_LIVE_ALLOWED=true``                      (master kill-switch)
      * ``BANXE_DYDX_SUBMIT_ENABLED=true``                   (per-venue kill-switch)
      * ``BANXE_DYDX_NODE_URL`` is syntactically valid       (testnet endpoint)

    Any other combination — flag off, missing/invalid URL, mock mode, partial
    config — returns ``"mock"`` (fail-closed; the spec forbids hard-failing on a
    partial config and forbids a silent live submit). The dYdX ExchangePort
    adapter is the only wired live ExchangePort route this sprint; nothing else
    is registered here.

    Note (ADR-083 self-custodial): even under the full combo, the order surface
    only constructs an UNSIGNED intent. Live submission transport is Phase-2b
    (separate operator GO + Ruflo sign-off + kill-switch arming); the adapter
    fences ``submit_signed_order`` independently via ``submission_enabled()``.
    """
    # Local import keeps the dse package independent of the ports package at
    # module load (the foundation is imported by app startup).
    from banxe_trading_backend.ports.dydx_exchange import is_valid_node_url

    if (
        settings.exchange_provider == DYDX_EXCHANGE_PROVIDER
        and settings.dse_provider_mode == "sandbox-live"
        and settings.dse_live_allowed
        and settings.dydx_submit_enabled
        and is_valid_node_url(settings.dydx_node_url)
    ):
        return DYDX_EXCHANGE_PROVIDER
    return "mock"
