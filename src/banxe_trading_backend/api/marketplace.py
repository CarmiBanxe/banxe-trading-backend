"""Ecosystem / marketplace router (S15 / X9.4) — INTERNAL, READ-ONLY, mock-safe.

GET /api/v1/marketplace/providers and /strategies expose a read-only registry
("vitrine") of ecosystem providers / strategies / agents. STRICTLY descriptive:
  * read-only (GET only, no body); NO purchases / subscriptions / activations;
  * NO entitlement, NO billing, NO tokens, NO keys, NO limits;
  * static fixtures only, no network; "click → trade" is NOT wired.
INTERNAL terminal endpoints — NOT a new external /v1 BaaS facade.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from banxe_trading_backend.marketplace import (
    MarketplaceStrategy,
    ProvidersResponse,
    StrategiesResponse,
    get_strategy,
    list_providers,
    list_strategies,
)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("/providers", response_model=ProvidersResponse)
async def providers(
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> ProvidersResponse:
    return ProvidersResponse(providers=list_providers(kind=kind, status=status))


@router.get("/strategies", response_model=StrategiesResponse)
async def strategies(
    provider_id: str | None = Query(default=None, alias="providerId"),
    category: str | None = Query(default=None),
    risk_profile: str | None = Query(default=None, alias="riskProfile"),
    status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
) -> StrategiesResponse:
    return StrategiesResponse(
        strategies=list_strategies(
            provider_id=provider_id,
            category=category,
            risk_profile=risk_profile,
            status=status,
            tag=tag,
        )
    )


@router.get("/strategies/{strategy_id}", response_model=MarketplaceStrategy)
async def strategy_detail(strategy_id: str) -> MarketplaceStrategy:
    strategy = get_strategy(strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"strategy {strategy_id!r} not found")
    return strategy
