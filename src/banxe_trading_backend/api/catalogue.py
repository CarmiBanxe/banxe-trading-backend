"""Catalogue meta router (M1.14) -- public read-only catalogue summary (counts + version).

GET /api/v1/catalogue/meta -> derived counts (symbols/instruments/markets/assets) + __version__.
NO balances, fees, execution, payments, or infra/ops/secret metrics. Does NOT touch or expose the
internal observability endpoints (/internal/*), which stay infra-fenced.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from banxe_trading_backend.meta.breakdown import (
    CatalogueBreakdown,
    InstrumentsBreakdown,
    catalogue_breakdown,
    instruments_breakdown,
)
from banxe_trading_backend.meta.catalogue import CatalogueMeta, catalogue_meta
from banxe_trading_backend.ports import MarketDataPort

from .deps import get_market_data

router = APIRouter(tags=["catalogue"])


@router.get("/catalogue/meta", response_model=CatalogueMeta)
async def get_catalogue_meta(
    market_data: MarketDataPort = Depends(get_market_data),
) -> CatalogueMeta:
    return catalogue_meta(market_data)


@router.get("/catalogue/breakdown", response_model=CatalogueBreakdown)
async def get_catalogue_breakdown(
    market_data: MarketDataPort = Depends(get_market_data),
) -> CatalogueBreakdown:
    # M1.16: read-only per-asset-class breakdown (derived; CatalogueMeta untouched).
    return catalogue_breakdown(market_data)


@router.get("/catalogue/instruments-breakdown", response_model=InstrumentsBreakdown)
async def get_instruments_breakdown() -> InstrumentsBreakdown:
    # M1.18: read-only instrument breakdown by fee-schedule/tick-size (derived; distinct path).
    return instruments_breakdown()

