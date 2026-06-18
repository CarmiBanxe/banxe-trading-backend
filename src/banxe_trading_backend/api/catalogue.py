"""Catalogue meta router (M1.14) -- public read-only catalogue summary (counts + version).

GET /api/v1/catalogue/meta -> derived counts (symbols/instruments/markets/assets) + __version__.
NO balances, fees, execution, payments, or infra/ops/secret metrics. Does NOT touch or expose the
internal observability endpoints (/internal/*), which stay infra-fenced.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from banxe_trading_backend.meta.catalogue import CatalogueMeta, catalogue_meta
from banxe_trading_backend.ports import MarketDataPort

from .deps import get_market_data

router = APIRouter(tags=["catalogue"])


@router.get("/catalogue/meta", response_model=CatalogueMeta)
async def get_catalogue_meta(
    market_data: MarketDataPort = Depends(get_market_data),
) -> CatalogueMeta:
    return catalogue_meta(market_data)
