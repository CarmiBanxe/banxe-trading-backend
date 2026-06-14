"""DSE recommend router (ADR-084, T7.1) — internal terminal endpoint.

POST /api/v1/dss/recommend → ranked, explainable, ADVISORY-ONLY recommendations.
No execution, no signing (self-custodial). The external BaaS endpoint
(POST /v1/dss/recommend, see docs/specs/dse-baas-api.yaml) is spec-only this
sprint — same engine, no Kong / partner keys / rate limits yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from banxe_trading_backend.dse import DseEngine, RecommendRequest, RecommendResponse


def get_dse_engine(request: Request) -> DseEngine:
    """Return the configured DSE engine (mock by default)."""
    engine: DseEngine = request.app.state.dse
    return engine


router = APIRouter(prefix="/dss", tags=["dss"])


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(
    body: RecommendRequest,
    engine: DseEngine = Depends(get_dse_engine),
) -> RecommendResponse:
    try:
        return await engine.recommend(body)
    except ValueError as exc:
        # e.g. riskProfile 'custom' without customWeights.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
