"""Educational gamification router (SBOX-5) — INTERNAL, sandbox/demo-only.

GET  /api/v1/sandbox/gamification/state   → the demo gamification state
POST /api/v1/sandbox/gamification/event   → apply a demo event (scenario/replay)

Demo-only: no real money, no tokens, no near-miss/VRRS, no link to real balances,
volumes, or PnL. Internal terminal endpoints — NOT on the external `/v1` facade.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from banxe_trading_backend.services.sandbox_gamification import (
    GamificationEventRequest,
    GamificationStateModel,
    SandboxGamificationStore,
    state_model,
)

router = APIRouter(prefix="/sandbox/gamification", tags=["sandbox"])


def _store(request: Request) -> SandboxGamificationStore:
    store: SandboxGamificationStore = request.app.state.sandbox_gamification
    return store


@router.get("/state", response_model=GamificationStateModel)
async def gamification_state(
    request: Request, profile_id: str | None = Query(default=None, alias="profileId")
) -> GamificationStateModel:
    return state_model(_store(request).get_state(profile_id))


@router.post("/event", response_model=GamificationStateModel)
async def gamification_event(
    body: GamificationEventRequest, request: Request
) -> GamificationStateModel:
    state = _store(request).apply_event(
        profile_id=body.profile_id,
        event_type=body.event_type,
        scenario_id=body.scenario_id,
        session_id=body.session_id,
    )
    return state_model(state)
