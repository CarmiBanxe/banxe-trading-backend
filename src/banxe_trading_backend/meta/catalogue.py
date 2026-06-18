"""Public read-only catalogue meta surface (M1.14, derived summary).

Derives the integer cardinalities of the already-migrated advisory catalogues (symbols,
instruments, markets, assets) and reuses the package ``__version__``. It is a DERIVED summary over
the existing list functions -- NOT a second registry, counter store, or version source.

READ-ONLY / advisory / mock-safe: NO balances, amounts, fees, execution, payments, or
infra/secret/ops metrics. Counts inherit the fail-closed behaviour of the underlying list
functions (a malformed catalogue entry is already skipped upstream); never a fabricated count.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from banxe_trading_backend import __version__
from banxe_trading_backend.assets.catalog import asset_catalog
from banxe_trading_backend.instruments.params import list_instruments
from banxe_trading_backend.instruments.xref import list_instrument_asset_xref
from banxe_trading_backend.models import CamelModel

if TYPE_CHECKING:
    from banxe_trading_backend.ports import MarketDataPort


class CatalogueMeta(CamelModel):
    """Read-only derived counts + version for the advisory catalogues (not a data source)."""

    symbols_count: int
    instruments_count: int
    markets_count: int
    assets_count: int
    version: str
    source: str


def catalogue_meta(market_data: MarketDataPort) -> CatalogueMeta:
    """Derive catalogue counts from the existing list functions + reuse ``__version__``."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    return CatalogueMeta(
        symbols_count=len(market_data.list_symbols()),
        instruments_count=len(list_instruments()),
        markets_count=len(list_instrument_asset_xref()),
        assets_count=len(asset_catalog(market_data).assets),
        version=__version__,
        source=SANDBOX_MOCK,
    )
