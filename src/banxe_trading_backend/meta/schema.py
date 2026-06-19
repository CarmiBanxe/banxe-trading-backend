"""Schema inventory (M1.25) -- static config-as-data inventory of the advisory DTO/schema families
published by the BANXE.RAR -> EMI migration lane.

Third meta/inventory slice, distinct (no overlap) from:
  - ``catalogue_meta`` (M1.14)        -- counts of catalogue DATA rows (symbols/instruments/...);
  - advisory-surface manifest (M1.24) -- advisory ENDPOINT families;
  - this module (M1.25)               -- advisory DTO/SCHEMA families.
Reuses the package ``__version__`` -- NOT a second version source.

Config-as-data ONLY: the family->DTO-name map is an explicit curated list, NEVER a programmatic
import/reflection scan (``__subclasses__()``). By construction it excludes live/regulated/auth/
orderbook/quote DTOs (PlaceOrderRequest, ExchangeOrderRequest, OrderResult, CancelResult,
RawOrderBook*/Ws*, Nonce/Verify/Session, RateQuote/QuoteRequest/QuoteResponse). READ-ONLY /
advisory / mock-safe: NO balances, postings, payments, APY, fees, uptime, latency, infra metrics.
"""
from __future__ import annotations

from banxe_trading_backend import __version__
from banxe_trading_backend.models import CamelModel

# Config-as-data: curated advisory DTO families (M-track only). NOT an import/reflection scan.
_SCHEMA_FAMILIES: dict[str, tuple[str, ...]] = {
    "earn": (
        "RateCard",
        "EarnRatesResponse",
        "EarnStatement",
        "EarnStatementResponse",
        "RiskBandDescriptor",
        "AdvisoryStatusDescriptor",
        "LockupTenorDescriptor",
        "EarnTaxonomy",
        "EarnMetrics",
    ),
    "accounts": ("AccountAdvisoryMetadata", "AccountMetadataResponse"),
    "assets": ("CryptoAssetMetadata", "AssetCatalogResponse"),
    "instruments": ("SymbolInfo", "InstrumentInfo", "InstrumentAssetXref"),
    "catalogue-meta": ("CatalogueMeta",),
    "breakdown": (
        "AssetClassCount",
        "CatalogueBreakdown",
        "MarketAssetCount",
        "MarketsBreakdown",
        "InstrumentDimensionCount",
        "InstrumentsBreakdown",
        "SymbolDimensionCount",
        "SymbolsBreakdown",
        "AccountDimensionCount",
        "AccountsBreakdown",
        "NetworkCount",
        "NetworkBreakdown",
        "CapabilityCount",
        "CapabilityBreakdown",
        "SupportedAssetCount",
        "SupportedAssetBreakdown",
    ),
    "manifest": ("AdvisorySurfaceFamily", "AdvisorySurfaceManifest"),
}


class SchemaFamily(CamelModel):
    """Count of advisory DTOs published under one schema family (integer meta)."""

    family: str
    dto_count: int


class SchemaInventory(CamelModel):
    """Read-only static config-as-data inventory of advisory DTO/schema families (derived).

    Enumerates the advisory DTO families (config-as-data, NOT an import scan) and reuses the
    package ``__version__``. Excludes live/regulated/auth/orderbook/quote DTOs by construction.
    """

    families: list[SchemaFamily]
    total_families: int
    total_dtos: int
    version: str
    source: str


def schema_inventory() -> SchemaInventory:
    """Derive the schema inventory from the curated config (deterministic; reuse version)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    families = [
        SchemaFamily(family=f, dto_count=len(_SCHEMA_FAMILIES[f]))
        for f in sorted(_SCHEMA_FAMILIES)
    ]
    return SchemaInventory(
        families=families,
        total_families=len(families),
        total_dtos=sum(len(v) for v in _SCHEMA_FAMILIES.values()),
        version=__version__,
        source=SANDBOX_MOCK,
    )
