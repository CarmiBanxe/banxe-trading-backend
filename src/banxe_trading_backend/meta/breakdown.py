"""Public read-only catalogue breakdown (M1.16, derived per-asset-class counts).

Derives the per-``asset_class`` cardinalities (crypto / stablecoin / fiat) of the advisory asset
catalogue by grouping ``asset_catalog(market_data).assets`` on ``CryptoAssetMetadata.asset_class``.
A DERIVED summary over the existing asset catalogue -- NOT a second registry, counter store,
version source, or asset map; it does NOT mutate the frozen ``CatalogueMeta``.

READ-ONLY / advisory / mock-safe: integer meta counts ONLY -- NO balances, amounts, APY/rates,
fees, execution, or payments. Counts inherit the fail-closed ``asset_catalog`` (malformed entries
already skipped upstream); never a fabricated count or class.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from banxe_trading_backend.assets.catalog import asset_catalog
from banxe_trading_backend.instruments.params import list_instruments
from banxe_trading_backend.instruments.xref import list_instrument_asset_xref
from banxe_trading_backend.models import CamelModel

if TYPE_CHECKING:
    from banxe_trading_backend.ports import MarketDataPort

# deterministic display ordering: canonical classes first, any extras appended sorted.
_CLASS_ORDER = ("crypto", "stablecoin", "fiat")


class AssetClassCount(CamelModel):
    """Count of catalogued assets in one asset class (integer meta; not a money value)."""

    asset_class: str
    count: int


class CatalogueBreakdown(CamelModel):
    """Read-only per-asset-class breakdown of the asset catalogue (derived summary; not a SoT)."""

    breakdown: list[AssetClassCount]
    total: int
    source: str


def catalogue_breakdown(market_data: MarketDataPort) -> CatalogueBreakdown:
    """Group the asset catalogue by ``asset_class`` (deterministic; fail-closed)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    counts: dict[str, int] = {}
    for asset in asset_catalog(market_data).assets:
        counts[asset.asset_class] = counts.get(asset.asset_class, 0) + 1
    ordered = [c for c in _CLASS_ORDER if c in counts] + sorted(
        c for c in counts if c not in _CLASS_ORDER
    )
    return CatalogueBreakdown(
        breakdown=[AssetClassCount(asset_class=c, count=counts[c]) for c in ordered],
        total=sum(counts.values()),
        source=SANDBOX_MOCK,
    )



class MarketAssetCount(CamelModel):
    """Count of markets in which one asset appears as base or quote (integer meta)."""

    asset: str
    count: int


class MarketsBreakdown(CamelModel):
    """Read-only per-base / per-quote market breakdown (derived summary; not a SoT)."""

    by_base: list[MarketAssetCount]
    by_quote: list[MarketAssetCount]
    total: int
    source: str


def markets_breakdown() -> MarketsBreakdown:
    """Count base/quote assets over the markets bundle (deterministic; fail-closed)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    markets = list_instrument_asset_xref()
    base_counts: dict[str, int] = {}
    quote_counts: dict[str, int] = {}
    for m in markets:
        base_counts[m.base_asset.asset] = base_counts.get(m.base_asset.asset, 0) + 1
        quote_counts[m.quote_asset.asset] = quote_counts.get(m.quote_asset.asset, 0) + 1

    def _to_list(counts: dict[str, int]) -> list[MarketAssetCount]:
        return [MarketAssetCount(asset=a, count=counts[a]) for a in sorted(counts)]

    return MarketsBreakdown(
        by_base=_to_list(base_counts),
        by_quote=_to_list(quote_counts),
        total=len(markets),
        source=SANDBOX_MOCK,
    )



class InstrumentDimensionCount(CamelModel):
    """Count of instruments sharing one value of a categorical dimension (integer meta)."""

    key: str
    count: int


class InstrumentsBreakdown(CamelModel):
    """Read-only instrument breakdown by fee-schedule / tick-size (derived summary; not a SoT)."""

    by_fee_schedule: list[InstrumentDimensionCount]
    by_tick_size: list[InstrumentDimensionCount]
    total: int
    source: str


def instruments_breakdown() -> InstrumentsBreakdown:
    """Count instruments by fee_schedule_ref / tick_size over list_instruments (deterministic)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    instruments = list_instruments()
    fee_counts: dict[str, int] = {}
    tick_counts: dict[str, int] = {}
    for inst in instruments:
        fee_counts[inst.fee_schedule_ref] = fee_counts.get(inst.fee_schedule_ref, 0) + 1
        tick_counts[inst.tick_size] = tick_counts.get(inst.tick_size, 0) + 1

    def _to_list(counts: dict[str, int]) -> list[InstrumentDimensionCount]:
        return [InstrumentDimensionCount(key=k, count=counts[k]) for k in sorted(counts)]

    return InstrumentsBreakdown(
        by_fee_schedule=_to_list(fee_counts),
        by_tick_size=_to_list(tick_counts),
        total=len(instruments),
        source=SANDBOX_MOCK,
    )
