"""DSE recommend router (ADR-084, T7.1) — internal terminal endpoint.

POST /api/v1/dss/recommend → ranked, explainable, ADVISORY-ONLY recommendations.
No execution, no signing (self-custodial). The external BaaS endpoint
(POST /v1/dss/recommend, see docs/specs/dse-baas-api.yaml) is spec-only this
sprint — same engine, no Kong / partner keys / rate limits yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from banxe_trading_backend.dse import DseEngine, RecommendRequest, RecommendResponse
from banxe_trading_backend.services.decision_lineage import record_lineage

_DEBUG_TRUTHY = {"1", "true", "yes", "on"}


def get_dse_engine(request: Request) -> DseEngine:
    """Return the configured DSE engine (mock by default)."""
    engine: DseEngine = request.app.state.dse
    return engine


router = APIRouter(prefix="/dss", tags=["dss"])


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(
    body: RecommendRequest,
    request: Request,
    engine: DseEngine = Depends(get_dse_engine),
    x_banxe_dse_debug: str | None = Header(default=None),
) -> RecommendResponse:
    # T7.8: the header only REQUESTS the sandbox decision-trace; the engine still
    # requires the operator env flag (BANXE_DSE_DEBUG_ENABLED) to emit it, so
    # production never returns a trace regardless of this header.
    debug = (x_banxe_dse_debug or "").strip().lower() in _DEBUG_TRUTHY
    try:
        response = await engine.recommend(body, debug=debug)
    except ValueError as exc:
        # e.g. riskProfile 'custom' without customWeights.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # G1L: inert audit capture (fail-closed; never changes the response).
    record_lineage(request, layer="DSE", body=body, response=response)
    return response
