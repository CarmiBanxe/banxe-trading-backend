"""Instrument <-> asset cross-reference advisory view (M1.11, read-only composition).

Composes existing advisory sources into one read-only view: a symbol's ``InstrumentInfo`` (M1.9)
plus the ``CryptoAssetMetadata`` (M1.8) of its base/quote assets, split via ``split_symbol``. It
is a composition VIEW over existing DTOs -- NOT a new catalogue/registry/source-of-truth. Reuses
``instrument_info`` + ``asset_metadata`` + ``split_symbol``; introduces no second asset/instrument
map.

READ-ONLY / advisory / mock-safe: NO balances, fees, execution, payments, or wallet ops.
fail-closed: an unknown symbol propagates ``InstrumentParamsError`` (mapped to 404 at the route).
"""
from __future__ import annotations

from banxe_trading_backend.assets.catalog import CryptoAssetMetadata, asset_metadata
from banxe_trading_backend.instruments.params import instrument_info, list_instruments
from banxe_trading_backend.models import CamelModel, InstrumentInfo, split_symbol


class InstrumentAssetXref(CamelModel):
    """Read-only cross-reference: instrument + its base/quote asset metadata (composition)."""

    symbol: str
    instrument: InstrumentInfo
    base_asset: CryptoAssetMetadata
    quote_asset: CryptoAssetMetadata


def instrument_asset_xref(symbol: str) -> InstrumentAssetXref:
    """Compose the instrument<->asset cross-reference for a symbol (fail-closed on unknown)."""
    instrument = instrument_info(symbol)  # raises InstrumentParamsError on an unknown symbol
    base, quote = split_symbol(instrument.symbol)
    return InstrumentAssetXref(
        symbol=instrument.symbol,
        instrument=instrument,
        base_asset=asset_metadata(base),
        quote_asset=asset_metadata(quote),
    )



def list_instrument_asset_xref() -> list[InstrumentAssetXref]:
    """Deterministic markets bundle: the cross-reference for every configured instrument.

    Reuses list_instruments() (sorted _INSTRUMENT_PARAMS) + instrument_asset_xref -- no new DTO,
    no second market catalogue. Fail-closed: a malformed/unresolvable entry is skipped (never a
    fabricated market).
    """
    out: list[InstrumentAssetXref] = []
    for instrument in list_instruments():
        try:
            out.append(instrument_asset_xref(instrument.symbol))
        except Exception:
            continue  # fail-closed: skip unresolvable entry (no fabricated market)
    return out
