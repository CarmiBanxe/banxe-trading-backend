"""Assets BaaS router (M1.8) -- read-only advisory crypto asset catalogue metadata.

GET /api/v1/assets/metadata -> descriptive per-asset metadata, reusing the trading symbol
asset universe (MarketDataPort.list_symbols()/SymbolInfo). NO balances, transactions, wallet
operations, deposits, withdrawals, transfers, or payments. Does NOT change /symbols or
/instruments/{symbol}.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from banxe_trading_backend.assets.catalog import AssetCatalogResponse, asset_catalog
from banxe_trading_backend.ports import MarketDataPort

from .deps import get_market_data

router = APIRouter(tags=["assets"])


@router.get("/assets/metadata", response_model=AssetCatalogResponse)
async def get_asset_metadata(
    market_data: MarketDataPort = Depends(get_market_data),
) -> AssetCatalogResponse:
    return asset_catalog(market_data)
