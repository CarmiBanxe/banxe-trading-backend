"""Symbols / instruments REST router (ADR-021 §D3).

TODO(ADR-021 governance): the real symbols/instruments catalogue source is
undecided. The skeleton serves the MarketDataPort mock catalogue + a stub
instrument descriptor.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from banxe_trading_backend.models import InstrumentInfo, SymbolInfo, split_symbol
from banxe_trading_backend.ports import MarketDataPort

from .deps import get_market_data

router = APIRouter(tags=["symbols"])


@router.get("/symbols", response_model=list[SymbolInfo])
async def list_symbols(
    market_data: MarketDataPort = Depends(get_market_data),
) -> list[SymbolInfo]:
    return market_data.list_symbols()


@router.get("/instruments/{symbol}", response_model=InstrumentInfo)
async def get_instrument(symbol: str) -> InstrumentInfo:
    base, quote = split_symbol(symbol)
    # Stub descriptor; real tick/min/max/fee come from the catalogue source (TODO).
    return InstrumentInfo(
        symbol=f"{base}-{quote}",
        tick_size="0.01",
        min_qty="0.0001",
        max_qty="1000",
        fee_schedule_ref="default",
    )
