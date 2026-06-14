"""Internal observability/readiness endpoints for DSE BaaS (T8.2).

INTERNAL ONLY — NOT part of the partner BaaS surface. These routes are excluded
from the OpenAPI schema (`include_in_schema=False`) and are intended to be fenced
to ops/cluster networks at the ingress layer. They expose readiness + metrics for
a future prod rollout; they perform NO execution and return NO secrets/PII.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from banxe_trading_backend.observability import BaasMetrics, dse_baas_health

# Internal namespace; hidden from the public OpenAPI/BaaS spec.
router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


@router.get("/health/dse-baas")
async def health_dse_baas(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    result = await dse_baas_health(
        sandbox_enabled=settings.dse_baas_sandbox_enabled,
        engine=request.app.state.dse,
        provider_mode=request.app.state.dse_provider_profile.mode,
    )
    # OK/DEGRADED → 200 (component alive); ERROR → 503 (dry-run failed).
    code = 503 if result["status"] == "ERROR" else 200
    return JSONResponse(result, status_code=code)


@router.get("/metrics/dse-baas")
async def metrics_dse_baas(request: Request) -> PlainTextResponse:
    metrics: BaasMetrics = request.app.state.baas_metrics
    return PlainTextResponse(
        metrics.render_prometheus(), media_type="text/plain; version=0.0.4"
    )
