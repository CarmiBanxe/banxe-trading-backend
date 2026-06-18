"""Catalogue meta router (M1.14) -- public read-only catalogue summary (counts + version).

GET /api/v1/catalogue/meta -> derived counts (symbols/instruments/markets/assets) + __version__.
NO balances, fees, execution, payments, or infra/ops/secret metrics. Does NOT touch or expose the
internal observability endpoints (/internal/*), which stay infra-fenced.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from banxe_trading_backend.meta.breakdown import (
    AccountsBreakdown,
    CatalogueBreakdown,
    InstrumentsBreakdown,
    NetworkBreakdown,
    SymbolsBreakdown,
    accounts_breakdown,
    catalogue_breakdown,
    instruments_breakdown,
    network_breakdown,
    symbols_breakdown,
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


@router.get("/catalogue/symbols-breakdown", response_model=SymbolsBreakdown)
async def get_symbols_breakdown(
    market_data: MarketDataPort = Depends(get_market_data),
) -> SymbolsBreakdown:
    # M1.19: read-only symbol breakdown by status/precision (derived; base/quote owned by M1.17).
    return symbols_breakdown(market_data)


@router.get("/catalogue/accounts-breakdown", response_model=AccountsBreakdown)
async def get_accounts_breakdown() -> AccountsBreakdown:
    # M1.20: read-only account breakdown by type/ledger-nature/status (derived; no balances).
    return accounts_breakdown()


@router.get("/catalogue/network-breakdown", response_model=NetworkBreakdown)
async def get_network_breakdown(
    market_data: MarketDataPort = Depends(get_market_data),
) -> NetworkBreakdown:
    # M1.21: read-only per-network asset breakdown (flatten of asset networks; derived).
    return network_breakdown(market_data)

