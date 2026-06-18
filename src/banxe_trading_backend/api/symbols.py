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
