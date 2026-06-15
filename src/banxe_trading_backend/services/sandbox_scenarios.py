"""Sandbox demo scenarios (SBOX-2) — INTERNAL, mock-safe, deterministic.

Canonical demo journeys layered over the already-delivered advisory seams (DSE,
mm / fees / quant / execution previews, marketplace) and the G1L lineage logger.
Each scenario is a static, deterministic walkthrough built from **mock payloads
only** — no live execution, no orders, no keys, no network, no real quotes. The
same input always yields the same walkthrough.

These are demonstrations of the advisory surface (recommendation → previews →
marketplace), NOT live trading. Internal-only — not exposed on the external `/v1`
facade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from banxe_trading_backend.models import CamelModel

StepKind = Literal[
    "dse-recommendation",
    "mm-preview",
    "fee-preview",
    "quant-preview",
    "execution-preview",
    "marketplace-card",
    "explanation",
]


@dataclass(frozen=True)
class SandboxStep:
    """One step in a demo walkthrough (mock request/response snippet)."""

    id: str
    kind: StepKind
    title: str
    description: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class SandboxScenario:
    """A deterministic demo journey over the advisory seams."""

    id: str
    name: str
    description: str
    steps: list[SandboxStep]
    tags: list[str] = field(default_factory=list)


# ----------------------------- wire (CamelModel) ---------------------------- #


class SandboxStepOut(CamelModel):
    id: str
    kind: str
    title: str
    description: str
    payload: dict[str, Any]


class SandboxScenarioOut(CamelModel):
    id: str
    name: str
    description: str
    steps: list[SandboxStepOut]
    tags: list[str]


class ScenarioSummary(CamelModel):
    id: str
    name: str
    description: str
    tags: list[str]


class ScenariosResponse(CamelModel):
    scenarios: list[ScenarioSummary]


# ------------------------------- mock payloads ------------------------------ #
# All values below are illustrative MOCK data — not real quotes/prices.

_UNSIGNED = {"signed": False, "submitted": False, "mode": "sandbox-mock"}


def _explanation(text: str) -> dict[str, Any]:
    return {"note": text, **{"mode": "sandbox-mock"}}


_SPOT_SWAP = SandboxScenario(
    id="spot-swap-demo",
    name="Spot Swap Demo",
    description="Walkthrough of a spot swap recommendation (advisory-only).",
    tags=["spot", "swap", "dse", "advisory"],
    steps=[
        SandboxStep(
            id="dss",
            kind="dse-recommendation",
            title="DSE recommends a SWAP",
            description="The DSE advises swapping into ETH (advisory, no execution).",
            payload={
                "request": {"asset": "ETH-USDC", "portfolioValueUsd": "10000"},
                "response": {"action": "SWAP", "asset": "ETH", "confidence": "0.71"},
            },
        ),
        SandboxStep(
            id="fees",
            kind="fee-preview",
            title="Fee preview",
            description="Advisory fee attribution for the candidate swap (mock).",
            payload={
                "request": {"venue": "lifi", "productType": "spot", "asset": "ETH",
                            "notionalUsd": "1000"},
                "response": {"totalFeeBps": "8.00", "totalFeeUsd": "0.80", **_UNSIGNED},
            },
        ),
        SandboxStep(
            id="quant",
            kind="quant-preview",
            title="Quant preview",
            description="Advisory quant analytics for the swap horizon (mock).",
            payload={
                "request": {"asset": "ETH", "productType": "spot", "notionalUsd": "1000",
                            "horizonDays": 7},
                "response": {"volatilityRegime": "normal", "fairValueGapBps": "12.00"},
            },
        ),
        SandboxStep(
            id="execution",
            kind="execution-preview",
            title="Unsigned execution preview",
            description="Multi-venue UNSIGNED preview — nothing is signed or submitted.",
            payload={
                "request": {"intentType": "swap", "asset": "ETH", "quoteAsset": "USDC",
                            "notionalUsd": "1000", "productType": "spot",
                            "executionMode": "preview-only"},
                "response": {"bestCandidate": {"venue": "lifi", "expectedPrice": "3493.70",
                                               **_UNSIGNED}, **_UNSIGNED},
            },
        ),
        SandboxStep(
            id="marketplace",
            kind="marketplace-card",
            title="Marketplace card — LI.FI",
            description="A read-only ecosystem card for the swap route provider.",
            payload={"provider": {"id": "lifi", "kind": "aggregator", "status": "listed"}},
        ),
        SandboxStep(
            id="explain",
            kind="explanation",
            title="Recap",
            description="Advisory-only walkthrough: nothing was signed, submitted, or charged.",
            payload=_explanation("Sandbox demo — advisory only, unsigned, no live execution."),
        ),
    ],
)

_PERP_HEDGE = SandboxScenario(
    id="perp-hedge-demo",
    name="Perp Hedge Demo",
    description="Walkthrough of hedging via a perpetual (advisory-only, no live).",
    tags=["perp", "hedge", "dse", "advisory"],
    steps=[
        SandboxStep(
            id="dss",
            kind="dse-recommendation",
            title="DSE recommends a hedge",
            description="The DSE advises a short-perp hedge against an ETH position.",
            payload={
                "request": {"asset": "ETH-USD", "portfolioValueUsd": "25000"},
                "response": {"action": "HEDGE", "asset": "ETH", "side": "short"},
            },
        ),
        SandboxStep(
            id="mm",
            kind="mm-preview",
            title="Market-making preview",
            description="Advisory quote ladder around the mid (mock).",
            payload={
                "request": {"asset": "ETH-USD", "spreadBps": 10, "levels": 2},
                "response": {"mode": "sandbox-mock", "rungs": 2, **_UNSIGNED},
            },
        ),
        SandboxStep(
            id="fees",
            kind="fee-preview",
            title="Fee preview",
            description="Advisory fee attribution for the hedge (mock).",
            payload={
                "request": {"venue": "dydx-v4", "productType": "perp", "asset": "ETH",
                            "notionalUsd": "5000"},
                "response": {"totalFeeBps": "5.00", "totalFeeUsd": "2.50", **_UNSIGNED},
            },
        ),
        SandboxStep(
            id="quant",
            kind="quant-preview",
            title="Quant preview",
            description="Advisory stress/vol analytics for the hedge (mock).",
            payload={
                "request": {"asset": "ETH", "productType": "perp", "notionalUsd": "5000",
                            "horizonDays": 14},
                "response": {"volatilityRegime": "elevated", "stressDrawdownPct": "18.00"},
            },
        ),
        SandboxStep(
            id="execution",
            kind="execution-preview",
            title="Unsigned execution preview",
            description="UNSIGNED perp preview on dydx-v4 — nothing signed or submitted.",
            payload={
                "request": {"intentType": "hedge", "asset": "ETH", "notionalUsd": "5000",
                            "productType": "perp", "executionMode": "preview-only"},
                "response": {"bestCandidate": {"venue": "dydx-v4", **_UNSIGNED}, **_UNSIGNED},
            },
        ),
    ],
)

_YIELD_REBALANCE = SandboxScenario(
    id="yield-rebalance-demo",
    name="Yield Rebalance Demo",
    description="Walkthrough of an earn/staking rebalance recommendation (advisory-only).",
    tags=["earn", "yield", "rebalance", "dse", "advisory"],
    steps=[
        SandboxStep(
            id="dss",
            kind="dse-recommendation",
            title="DSE recommends a REBALANCE",
            description="The DSE advises rebalancing idle USDC into an earn strategy.",
            payload={
                "request": {"asset": "USDC", "portfolioValueUsd": "50000"},
                "response": {"action": "REBALANCE", "asset": "USDC", "target": "earn"},
            },
        ),
        SandboxStep(
            id="fees",
            kind="fee-preview",
            title="Fee preview",
            description="Advisory fee attribution for the rebalance (mock).",
            payload={
                "request": {"venue": "aave-v3", "productType": "earn", "asset": "USDC",
                            "notionalUsd": "20000"},
                "response": {"totalFeeBps": "3.00", "totalFeeUsd": "6.00", **_UNSIGNED},
            },
        ),
        SandboxStep(
            id="quant",
            kind="quant-preview",
            title="Quant preview",
            description="Advisory yield/risk analytics for the rebalance (mock).",
            payload={
                "request": {"asset": "USDC", "productType": "earn", "notionalUsd": "20000",
                            "horizonDays": 30},
                "response": {"volatilityRegime": "low", "expectedApyPct": "4.20"},
            },
        ),
        SandboxStep(
            id="marketplace",
            kind="marketplace-card",
            title="Marketplace card — earn strategy",
            description="A read-only ecosystem card for a yield strategy provider.",
            payload={"strategy": {"id": "aave-v3-usdc", "category": "earn", "status": "listed"}},
        ),
        SandboxStep(
            id="explain",
            kind="explanation",
            title="Recap",
            description="Advisory-only: a yield idea with previews; nothing was executed.",
            payload=_explanation("Sandbox demo — advisory only, unsigned, no live execution."),
        ),
    ],
)

_SCENARIOS: tuple[SandboxScenario, ...] = (_SPOT_SWAP, _PERP_HEDGE, _YIELD_REBALANCE)


def _step_out(step: SandboxStep) -> SandboxStepOut:
    return SandboxStepOut(
        id=step.id, kind=step.kind, title=step.title,
        description=step.description, payload=step.payload,
    )


def _scenario_out(scenario: SandboxScenario) -> SandboxScenarioOut:
    return SandboxScenarioOut(
        id=scenario.id, name=scenario.name, description=scenario.description,
        steps=[_step_out(s) for s in scenario.steps], tags=list(scenario.tags),
    )


def list_scenarios() -> list[ScenarioSummary]:
    """Return the deterministic scenario summaries (no steps)."""
    return [
        ScenarioSummary(id=s.id, name=s.name, description=s.description, tags=list(s.tags))
        for s in _SCENARIOS
    ]


def get_scenario(scenario_id: str) -> SandboxScenarioOut | None:
    """Return the full scenario with steps, or None if unknown."""
    for s in _SCENARIOS:
        if s.id == scenario_id:
            return _scenario_out(s)
    return None
