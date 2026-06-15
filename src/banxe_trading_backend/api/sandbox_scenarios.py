"""Sandbox demo-scenarios router (SBOX-2) — INTERNAL, mock-safe, read-only.

GET /api/v1/sandbox/scenarios            → list of demo-scenario summaries
GET /api/v1/sandbox/scenarios/{id}       → full deterministic walkthrough (steps)

Deterministic, mock-only walkthroughs over the delivered advisory seams — no live
execution, no orders, no keys, no network. Internal terminal endpoints — NOT part
of the external `/v1` BaaS facade.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from banxe_trading_backend.services.sandbox_scenarios import (
    SandboxScenarioOut,
    ScenariosResponse,
    get_scenario,
    list_scenarios,
)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


@router.get("/scenarios", response_model=ScenariosResponse)
async def scenarios() -> ScenariosResponse:
    return ScenariosResponse(scenarios=list_scenarios())


@router.get("/scenarios/{scenario_id}", response_model=SandboxScenarioOut)
async def scenario_detail(scenario_id: str) -> SandboxScenarioOut:
    scenario = get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id!r} not found")
    return scenario
