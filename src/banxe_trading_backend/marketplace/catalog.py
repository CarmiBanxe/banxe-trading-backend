"""Ecosystem / marketplace registry (Sprint S15 / X9.4) — READ-ONLY, mock-safe.

A logical "vitrine" over the providers/strategies/agents described in the research
docs (LI.FI, dYdX, GMX, StakeKit, Hummingbot-based MM, quant). STRICTLY read-only
and mock-safe (ADR-092):
  * NO purchases / subscriptions / activations, NO tokens / revenue-share / payouts;
  * NO entitlement, NO billing, NO partner-tiers, NO keys, NO limits;
  * static fixtures only — no network, no external source;
  * descriptive cards only; "click → trade" is NOT wired — at most a card links to
    the already-existing advisory endpoints. CORE contracts are untouched.
"""

from __future__ import annotations

from banxe_trading_backend.models import CamelModel


class MarketplaceProvider(CamelModel):
    id: str
    kind: str  # execution | yield | mm | analytics
    name: str
    description: str
    status: str  # sandbox | experimental | planned
    links: dict[str, str]


class MarketplaceStrategy(CamelModel):
    id: str
    provider_id: str
    category: str  # market-making | yield | execution-routing | quant-analytics
    name: str
    description: str
    risk_profile: str  # conservative | balanced | aggressive
    status: str  # sandbox | experimental | planned
    tags: list[str]


class ProvidersResponse(CamelModel):
    providers: list[MarketplaceProvider]


class StrategiesResponse(CamelModel):
    strategies: list[MarketplaceStrategy]


# --- static registry (fixtures only; descriptive read-only cards) ------------ #

_PROVIDERS: list[MarketplaceProvider] = [
    MarketplaceProvider(
        id="lifi", kind="execution", name="LI.FI Aggregator",
        description="Cross-chain swap and bridge aggregator (sandbox profile).",
        status="sandbox",
        links={"website": "https://li.fi", "docs": "https://li.fi/developers"},
    ),
    MarketplaceProvider(
        id="dydx-v4", kind="execution", name="dYdX v4",
        description="Perps DEX; unsigned-intent execution (self-custodial).",
        status="sandbox", links={"website": "https://dydx.exchange"},
    ),
    MarketplaceProvider(
        id="gmx-v2", kind="execution", name="GMX v2",
        description="Perps / spot DEX with referral attribution (mock card).",
        status="experimental", links={},
    ),
    MarketplaceProvider(
        id="stakekit", kind="yield", name="StakeKit",
        description="Staking / yield aggregation (read-only rates in sandbox).",
        status="sandbox", links={},
    ),
    MarketplaceProvider(
        id="hummingbot-mm", kind="mm", name="Hummingbot-based MM program (mock)",
        description="Mock description of a market-making program built on Hummingbot.",
        status="planned", links={},
    ),
    MarketplaceProvider(
        id="remizov-quant-mock", kind="analytics", name="Remizov Quant (mock)",
        description="Mock quant-analytics provider (fair-value / scenario signals).",
        status="planned", links={},
    ),
]

_STRATEGIES: list[MarketplaceStrategy] = [
    MarketplaceStrategy(
        id="mm-avellaneda-mock", provider_id="hummingbot-mm", category="market-making",
        name="Avellaneda-Stoikov Mock Strategy",
        description="Mock Avellaneda-Stoikov strategy for educational purposes.",
        risk_profile="balanced", status="sandbox", tags=["mm", "avellaneda", "educational"],
    ),
    MarketplaceStrategy(
        id="yield-stable-mock", provider_id="stakekit", category="yield",
        name="Stablecoin Yield Mock",
        description="Mock stablecoin yield comparison strategy.",
        risk_profile="conservative", status="sandbox", tags=["yield", "stablecoin"],
    ),
    MarketplaceStrategy(
        id="quant-remizov-mock", provider_id="remizov-quant-mock", category="quant-analytics",
        name="Remizov Fair-Value Mock",
        description="Mock quant fair-value / stress-signal strategy.",
        risk_profile="aggressive", status="planned", tags=["quant", "fair-value", "stress"],
    ),
    MarketplaceStrategy(
        id="exec-lifi-route-mock", provider_id="lifi", category="execution-routing",
        name="LI.FI Route Preview Mock",
        description="Mock cross-chain routing preview strategy.",
        risk_profile="balanced", status="sandbox", tags=["execution", "routing"],
    ),
]


def list_providers(
    *, kind: str | None = None, status: str | None = None
) -> list[MarketplaceProvider]:
    return [
        p for p in _PROVIDERS
        if (kind is None or p.kind == kind) and (status is None or p.status == status)
    ]


def list_strategies(
    *,
    provider_id: str | None = None,
    category: str | None = None,
    risk_profile: str | None = None,
    status: str | None = None,
    tag: str | None = None,
) -> list[MarketplaceStrategy]:
    return [
        s for s in _STRATEGIES
        if (provider_id is None or s.provider_id == provider_id)
        and (category is None or s.category == category)
        and (risk_profile is None or s.risk_profile == risk_profile)
        and (status is None or s.status == status)
        and (tag is None or tag in s.tags)
    ]


def get_strategy(strategy_id: str) -> MarketplaceStrategy | None:
    return next((s for s in _STRATEGIES if s.id == strategy_id), None)
