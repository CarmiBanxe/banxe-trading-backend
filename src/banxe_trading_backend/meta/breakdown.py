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
