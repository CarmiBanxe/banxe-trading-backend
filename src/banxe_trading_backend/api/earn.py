"""Earn BaaS router (T7.5) — read-only sandbox Earn rate comparison.

GET /api/v1/earn/rates → current-yield comparison across a basket (advisory,
sandbox-mock). The external BaaS path is GET /v1/earn/rates (see
docs/specs/earn-api.yaml). READ-ONLY: NO stake/unstake, NO execution, NO keys,
NO network (self-custodial). Real StakeKit / Aave integration is a future sprint.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request

from banxe_trading_backend.earn.rates import (
    EarnRatesCatalog,
    EarnRatesResponse,
    earn_rates,
)

router = APIRouter(prefix="/earn", tags=["earn"])


@router.get("/rates", response_model=EarnRatesResponse)
async def get_rates(
    request: Request,
    assets: list[str] | None = Query(None, description="assets to compare; default basket"),
) -> EarnRatesResponse:
    catalog: EarnRatesCatalog = request.app.state.earn_rates
    return await earn_rates(
        catalog,
        assets=assets or [],
        now=datetime.now(UTC).isoformat(),
    )
