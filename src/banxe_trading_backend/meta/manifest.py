"""Advisory-surface manifest (M1.24) -- static config-as-data inventory of the advisory read-only
endpoint families published by the BANXE.RAR -> EMI migration lane.

Distinct from ``catalogue_meta`` (M1.14, which counts catalogue DATA rows): this manifest enumerates
the advisory SURFACE FAMILIES and reuses the package ``__version__`` -- NOT a second version source.

Config-as-data ONLY: the family->paths map is an explicit curated list, NEVER a programmatic
``app.routes`` scan. By construction it excludes infra/observability (/internal/*, /healthz) and
live/regulated/sandbox surfaces (orders, execution, fees, quant, market_making, marketplace,
sandbox*, baas_dss). READ-ONLY / advisory / mock-safe: NO balances, postings, payments, APY, fees,
uptime, latency, or any infra/ops metric.
"""
from __future__ import annotations

from banxe_trading_backend import __version__
from banxe_trading_backend.models import CamelModel

# Config-as-data: curated advisory read-only endpoint families (M-track only). NOT a route scan.
_ADVISORY_FAMILIES: dict[str, tuple[str, ...]] = {
    "earn": ("/earn/rates", "/earn/statement", "/earn/taxonomy"),
    "accounts": ("/accounts/metadata",),
    "assets": ("/assets/metadata", "/assets/{asset}/markets"),
    "symbols": (
        "/symbols",
        "/instruments",
        "/instruments/{symbol}",
        "/instruments/{symbol}/assets",
        "/markets",
        "/markets/breakdown",
    ),
    "catalogue": (
        "/catalogue/meta",
        "/catalogue/breakdown",
        "/catalogue/instruments-breakdown",
        "/catalogue/symbols-breakdown",
        "/catalogue/accounts-breakdown",
        "/catalogue/network-breakdown",
        "/catalogue/capability-breakdown",
        "/catalogue/supported-asset-breakdown",
    ),
}


class AdvisorySurfaceFamily(CamelModel):
    """Count of advisory read-only endpoints published under one family (integer meta)."""

    family: str
    endpoint_count: int


class AdvisorySurfaceManifest(CamelModel):
    """Read-only static config-as-data inventory of advisory surface families (not a data source).

    Enumerates the advisory read-only endpoint families (config-as-data, NOT a route scan) and
    reuses the package ``__version__``. Excludes infra (/internal/*, /healthz) and live/regulated/
    sandbox surfaces by construction.
    """

    families: list[AdvisorySurfaceFamily]
    total_families: int
    total_endpoints: int
    version: str
    source: str


def advisory_surface_manifest() -> AdvisorySurfaceManifest:
    """Derive the advisory-surface manifest from the curated config (deterministic)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    families = [
        AdvisorySurfaceFamily(family=f, endpoint_count=len(_ADVISORY_FAMILIES[f]))
        for f in sorted(_ADVISORY_FAMILIES)
    ]
    return AdvisorySurfaceManifest(
        families=families,
        total_families=len(families),
        total_endpoints=sum(len(p) for p in _ADVISORY_FAMILIES.values()),
        version=__version__,
        source=SANDBOX_MOCK,
    )
