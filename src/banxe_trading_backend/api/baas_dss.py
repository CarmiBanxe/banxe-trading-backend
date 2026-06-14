"""DSE BaaS sandbox facade (T8.1) — external advisory endpoint.

POST /v1/dss/recommend — a THIN facade for BaaS/TaaS partners over the SAME
internal DSE engine that already serves the terminal (POST /api/v1/dss/recommend).
ADVISORY-ONLY, SANDBOX-ONLY, MOCK-ONLY (ADR-084/085/086):
  * no execution, no signing, no staking, no wallet actions (self-custodial);
  * no live providers / market data / partner keys — only mock fixtures;
  * no billing, no partner tiering, no rate limits (future ODR);
  * no gamification / engagement mechanics — pure decision-support.

Sandbox gate: the facade is served ONLY when ``BANXE_DSE_BAAS_SANDBOX_ENABLED``
is True (sandbox/dev deployments). When the flag is off (production default) every
request returns 503 "sandbox disabled". Deployments MUST additionally fence this
endpoint to sandbox/dev hosts at the ingress/host layer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from banxe_trading_backend.dse import DseEngine, RecommendRequest, RecommendResponse

from .dss import _DEBUG_TRUTHY, get_dse_engine

# External BaaS path is /v1/dss/recommend (NOT under the internal /api/v1 prefix).
router = APIRouter(prefix="/v1/dss", tags=["baas-dss"])


@router.post("/recommend", response_model=RecommendResponse)
async def baas_recommend(
    body: RecommendRequest,
    request: Request,
    engine: DseEngine = Depends(get_dse_engine),
    x_banxe_dse_debug: str | None = Header(default=None),
) -> RecommendResponse:
    # Sandbox flag gate: production default is OFF → no external DSE BaaS.
    if not request.app.state.settings.dse_baas_sandbox_enabled:
        raise HTTPException(status_code=503, detail="DSE BaaS sandbox is disabled")
    # Thin facade: route straight into the internal advisory engine (mock-only).
    # The decisionTrace stays double-gated (also needs BANXE_DSE_DEBUG_ENABLED).
    debug = (x_banxe_dse_debug or "").strip().lower() in _DEBUG_TRUTHY
    try:
        return await engine.recommend(body, debug=debug)
    except ValueError as exc:
        # e.g. riskProfile 'custom' without customWeights.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
