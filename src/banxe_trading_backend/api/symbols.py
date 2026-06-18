"""Symbols / instruments REST router (ADR-021 §D3).

TODO(ADR-021 governance): the real symbols/instruments catalogue source is
undecided. The skeleton serves the MarketDataPort mock symbol catalogue;
instrument trading-parameters come from instruments.params (config-as-data, M1.9).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from banxe_trading_backend.instruments.params import (
    InstrumentParamsError,
    instrument_info,
    list_instruments,
)
from banxe_trading_backend.instruments.xref import (
    InstrumentAssetXref,
    instrument_asset_xref,
    list_instrument_asset_xref,
)
from banxe_trading_backend.meta.breakdown import MarketsBreakdown, markets_breakdown
from banxe_trading_backend.models import InstrumentInfo, SymbolInfo
from banxe_trading_backend.ports import MarketDataPort

from .deps import get_market_data

router = APIRouter(tags=["symbols"])


@router.get("/symbols", response_model=list[SymbolInfo])
async def list_symbols(
    market_data: MarketDataPort = Depends(get_market_data),
) -> list[SymbolInfo]:
    return market_data.list_symbols()


@router.get("/instruments", response_model=list[InstrumentInfo])
async def list_all_instruments() -> list[InstrumentInfo]:
    # M1.10: advisory list of the M1.9 instrument catalogue (single source: instruments.params).
    return list_instruments()


@router.get("/instruments/{symbol}", response_model=InstrumentInfo)
async def get_instrument(symbol: str) -> InstrumentInfo:
    # M1.9: config-as-data advisory trading parameters (single source: instruments.params);
    # fail-closed 404 for an unknown symbol (no fabricated stub). FeeEnginePort still owns fees.
    try:
        return instrument_info(symbol)
    except InstrumentParamsError as exc:
        raise HTTPException(status_code=404, detail=f"unknown instrument: {symbol}") from exc



@router.get("/instruments/{symbol}/assets", response_model=InstrumentAssetXref)
async def get_instrument_assets(symbol: str) -> InstrumentAssetXref:
    # M1.11: read-only composition of the instrument + its base/quote asset metadata.
    try:
        return instrument_asset_xref(symbol)
    except InstrumentParamsError as exc:
        raise HTTPException(status_code=404, detail=f"unknown instrument: {symbol}") from exc



@router.get("/markets", response_model=list[InstrumentAssetXref])
async def list_markets() -> list[InstrumentAssetXref]:
    # M1.12: read-only markets bundle = list of instrument<->asset cross-references.
    return list_instrument_asset_xref()


@router.get("/markets/breakdown", response_model=MarketsBreakdown)
async def get_markets_breakdown() -> MarketsBreakdown:
    # M1.17: read-only per-base/per-quote market counts (derived; xref bundle untouched).
    return markets_breakdown()
