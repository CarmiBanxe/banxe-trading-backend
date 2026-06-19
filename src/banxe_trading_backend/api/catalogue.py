"""Catalogue meta router (M1.14) -- public read-only catalogue summary (counts + version).

GET /api/v1/catalogue/meta -> derived counts (symbols/instruments/markets/assets) + __version__.
NO balances, fees, execution, payments, or infra/ops/secret metrics. Does NOT touch or expose the
internal observability endpoints (/internal/*), which stay infra-fenced.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from banxe_trading_backend.meta.breakdown import (
    AccountsBreakdown,
    CapabilityBreakdown,
    CatalogueBreakdown,
    InstrumentsBreakdown,
    NetworkBreakdown,
    SupportedAssetBreakdown,
    SymbolsBreakdown,
    accounts_breakdown,
    capability_breakdown,
    catalogue_breakdown,
    instruments_breakdown,
    network_breakdown,
    supported_asset_breakdown,
    symbols_breakdown,
)
from banxe_trading_backend.meta.catalogue import CatalogueMeta, catalogue_meta
from banxe_trading_backend.meta.changelog import (
    AdvisorySurfaceChangelog,
    advisory_surface_changelog,
)
from banxe_trading_backend.meta.manifest import AdvisorySurfaceManifest, advisory_surface_manifest
from banxe_trading_backend.meta.schema import SchemaInventory, schema_inventory
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


@router.get("/catalogue/capability-breakdown", response_model=CapabilityBreakdown)
async def get_capability_breakdown() -> CapabilityBreakdown:
    # M1.22: read-only per-capability account breakdown (flatten of account capabilities; derived).
    return capability_breakdown()


@router.get("/catalogue/supported-asset-breakdown", response_model=SupportedAssetBreakdown)
async def get_supported_asset_breakdown() -> SupportedAssetBreakdown:
    # M1.23: read-only per-supported-asset account breakdown (flatten; accounts-per-asset, derived).
    return supported_asset_breakdown()


@router.get("/catalogue/advisory-surface", response_model=AdvisorySurfaceManifest)
async def get_advisory_surface() -> AdvisorySurfaceManifest:
    # M1.24: read-only advisory-surface manifest (static config-as-data inventory).
    return advisory_surface_manifest()


@router.get("/catalogue/schema-inventory", response_model=SchemaInventory)
async def get_schema_inventory() -> SchemaInventory:
    # M1.25: read-only advisory DTO/schema-family inventory (static config-as-data; reuse version).
    return schema_inventory()


@router.get("/catalogue/changelog", response_model=AdvisorySurfaceChangelog)
async def get_advisory_changelog() -> AdvisorySurfaceChangelog:
    # M1.26: read-only advisory-surface changelog (static config-as-data substep provenance).
    return advisory_surface_changelog()

