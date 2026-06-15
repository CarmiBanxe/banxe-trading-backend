"""Sandbox session recorder & replay router (SBOX-3) — INTERNAL, mock-safe.

POST /api/v1/sandbox/sessions                  → create a session
POST /api/v1/sandbox/sessions/{id}/steps       → append a step reference
POST /api/v1/sandbox/sessions/{id}/finish      → finish (sets finishedAt + notes)
GET  /api/v1/sandbox/sessions                  → list summaries (limit/offset)
GET  /api/v1/sandbox/sessions/{id}             → one full summary

An observability layer over the advisory seams — no live execution, no orders, no
keys, no network. Internal terminal endpoints — NOT on the external `/v1` facade.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from banxe_trading_backend.services.sandbox_sessions import (
    AppendStepRequest,
    CreateSessionRequest,
    FinishSessionRequest,
    SandboxSessionStepRef,
    SandboxSessionStore,
    SessionsListResponse,
    SessionSummaryModel,
    session_summary_model,
)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


def _store(request: Request) -> SandboxSessionStore:
    store: SandboxSessionStore = request.app.state.sandbox_sessions
    return store


@router.post("/sessions", response_model=SessionSummaryModel)
async def create_session(body: CreateSessionRequest, request: Request) -> SessionSummaryModel:
    summary = _store(request).create_session(
        scenario_id=body.scenario_id, title=body.title, description=body.description
    )
    return session_summary_model(summary)


@router.post("/sessions/{session_id}/steps", response_model=SessionSummaryModel)
async def append_step(
    session_id: str, body: AppendStepRequest, request: Request
) -> SessionSummaryModel:
    step = SandboxSessionStepRef(
        scenario_id=body.scenario_id,
        step_id=body.step_id,
        layer=body.layer,
        lineage_event_id=body.lineage_event_id,
    )
    summary = _store(request).append_step(session_id, step)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    return session_summary_model(summary)


@router.post("/sessions/{session_id}/finish", response_model=SessionSummaryModel)
async def finish_session(
    session_id: str, body: FinishSessionRequest, request: Request
) -> SessionSummaryModel:
    summary = _store(request).finish_session(session_id, notes=body.notes)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    return session_summary_model(summary)


@router.get("/sessions", response_model=SessionsListResponse)
async def list_sessions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SessionsListResponse:
    summaries = _store(request).list_sessions(limit=limit, offset=offset)
    return SessionsListResponse(sessions=[session_summary_model(s) for s in summaries])


@router.get("/sessions/{session_id}", response_model=SessionSummaryModel)
async def get_session(session_id: str, request: Request) -> SessionSummaryModel:
    summary = _store(request).get_session(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    return session_summary_model(summary)
