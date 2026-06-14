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

import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from banxe_trading_backend.dse import DseEngine, RecommendRequest, RecommendResponse
from banxe_trading_backend.observability import log_baas_event

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
    # Thin facade: route straight into the internal advisory engine (mock-only).
    # The decisionTrace stays double-gated (also needs BANXE_DSE_DEBUG_ENABLED).
    debug = (x_banxe_dse_debug or "").strip().lower() in _DEBUG_TRUTHY
    started = time.perf_counter()
    status = 200
    resp: RecommendResponse | None = None
    try:
        # Sandbox flag gate: production default is OFF → no external DSE BaaS.
        if not request.app.state.settings.dse_baas_sandbox_enabled:
            status = 503
            raise HTTPException(status_code=503, detail="DSE BaaS sandbox is disabled")
        try:
            resp = await engine.recommend(body, debug=debug)
        except ValueError as exc:
            # e.g. riskProfile 'custom' without customWeights.
            status = 422
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return resp
    finally:
        # T8.2 internal observability: metrics + a sanitized structured log.
        # NO secrets/PII — no amounts, no positions, only aggregate summary.
        latency_ms = (time.perf_counter() - started) * 1000
        top = resp.recommendations[0] if (resp and resp.recommendations) else None
        profile = request.app.state.dse_provider_profile  # T8.3: safe descriptor
        request.app.state.baas_metrics.observe(
            asset=body.asset,
            risk_profile=body.risk_profile.value,
            status=status,
            latency_ms=latency_ms,
            top_action_type=(top.action.type.value if top else None),
            debug=debug,
            provider_mode=profile.mode,
        )
        log_baas_event(
            {
                "event": "dse_baas_recommend",
                "traceId": (resp.trace_id if resp else None),
                "asset": body.asset,
                "riskProfile": body.risk_profile.value,
                "status": status,
                "latencyMs": round(latency_ms, 3),
                "includeSentiment": body.include_sentiment,
                "includeStressTests": body.include_stress_tests,
                "topActionType": (top.action.type.value if top else None),
                "topDriver": (top.top_driver if top else None),
                "topUtilityScore": (top.utility_score if top else None),
                "enrichmentApplied": (resp.analytics_context is not None) if resp else False,
                "decisionTraceEmitted": (resp.decision_trace is not None) if resp else False,
                # T8.3: safe provider wiring descriptor — NO keys/endpoints.
                "providerMode": profile.mode,
                "providerProfile": profile.to_dict(),
            }
        )
