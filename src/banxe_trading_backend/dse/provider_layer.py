"""Unified DSE provider-layer & safety-rails (T8.3) — wiring only, mock-default.

A single resolution + safety point for the DSE data-source providers
(market / risk, sentiment, stress, earn). It introduces the configuration and
architectural seams needed to select a future live implementation **without**
shipping one: the ONLY working mode is ``mock`` and the default everywhere stays
``mock``. Anything other than mock is an OPERATOR DECISION (ODR) — it is rejected
fast (no live keys, no live API, no behaviour change).

This layer changes NO utility, NO ranking, NO request/response contract. It only
exposes safe (non-secret) provider descriptors for observability and a startup
guard that refuses to run with a not-yet-implemented live configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from banxe_trading_backend.config import Settings

#: The only implemented provider value this sprint.
MOCK = "mock"

#: DSE data-source domains behind the provider-layer.
PROVIDER_DOMAINS = ("market", "sentiment", "stress", "earn")


class ProviderMode(str, Enum):
    """DSE provider operating mode. Only ``MOCK`` is implemented (T8.3)."""

    MOCK = "mock"
    SANDBOX_LIVE = "sandbox-live"  # future, ODR-gated
    PROD_LIVE = "prod-live"  # future, ODR-gated


@dataclass(frozen=True)
class ProviderProfile:
    """Safe, NON-secret descriptor of the active provider wiring (observability).

    Carries provider *names/modes* only — never API keys or endpoints.
    """

    mode: str
    market: str
    sentiment: str
    stress: str
    earn: str

    def to_dict(self) -> dict[str, str]:
        return {
            "mode": self.mode,
            "market": self.market,
            "sentiment": self.sentiment,
            "stress": self.stress,
            "earn": self.earn,
        }


class LiveProviderNotWiredError(ValueError):
    """Raised when a non-mock provider/mode is requested — ODR, not implemented."""


def resolve_mode(value: str) -> ProviderMode:
    """Parse a provider-mode string into the enum (raises on unknown value)."""
    try:
        return ProviderMode(value)
    except ValueError as exc:
        valid = ", ".join(m.value for m in ProviderMode)
        raise LiveProviderNotWiredError(
            f"unknown DSE provider mode {value!r}; valid: {valid}"
        ) from exc


def provider_profile(settings: Settings) -> ProviderProfile:
    """Build the safe provider descriptor from settings (no secrets)."""
    return ProviderProfile(
        mode=settings.dse_provider_mode,
        market=settings.dse_market_provider,
        sentiment=settings.dse_sentiment_provider,
        stress=settings.dse_stress_provider,
        earn=settings.dse_earn_provider,
    )


def assert_mock_only(settings: Settings) -> None:
    """Startup safety-rail: refuse non-mock DSE provider mode/value (ODR), with
    the **narrow** S6.2-EN exception for the dYdX public market-data route.

    The live implementations do not exist yet, so a non-mock configuration must
    fail fast rather than silently degrade — except for the one wired live route:
    sandbox-live mode + ``dse_market_provider=dydx`` + ``dse_live_allowed=true``
    routes market-data to the public dYdX Indexer (S6.2-EN). All OTHER domains
    must still resolve to mock. A partial sandbox-live config (e.g. kill-switch
    off) fail-closes to mock at runtime — it does NOT raise (spec: never
    hard-fail). ``prod-live`` mode remains ODR-gated.
    """
    mode = resolve_mode(settings.dse_provider_mode)
    if mode is ProviderMode.PROD_LIVE:
        raise LiveProviderNotWiredError(
            f"DSE provider mode {mode.value!r} is OPERATOR-GATED (ODR); "
            "only 'mock' and the sandbox-live dYdX market route are wired this sprint"
        )
    # The only wired non-mock domain value is market=dydx (S6.2-EN). Anything
    # else with a non-mock value is an unwired live provider → fail fast.
    non_mock: dict[str, str] = {}
    for domain, value in {
        "market": settings.dse_market_provider,
        "sentiment": settings.dse_sentiment_provider,
        "stress": settings.dse_stress_provider,
        "risk": settings.dse_risk_provider,
        "earn": settings.dse_earn_provider,
        "risk_greeks": settings.risk_greeks_provider,
        "earn_rates": settings.earn_rates_provider,
    }.items():
        if value == MOCK:
            continue
        if domain == "market" and value == "dydx":
            # S6.2-EN-wired live route; kill-switch off → runtime fail-closes to
            # mock (not raised here). Any other dydx-without-combo case is also
            # tolerated and fail-closed at the build step.
            continue
        non_mock[domain] = value
    if non_mock:
        raise LiveProviderNotWiredError(
            f"non-mock DSE providers are OPERATOR-GATED (ODR), not wired: {non_mock}"
        )
