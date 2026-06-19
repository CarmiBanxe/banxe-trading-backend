"""Advisory-surface changelog (M1.26) -- static config-as-data ordered provenance of the M1.x
advisory substeps published in this backend build.

Fourth meta/inventory slice, distinct (no overlap) from:
  - ``catalogue_meta`` (M1.14)        -- counts of catalogue DATA rows;
  - advisory-surface manifest (M1.24) -- advisory ENDPOINT families;
  - schema inventory (M1.25)          -- advisory DTO/SCHEMA families;
  - this module (M1.26)               -- advisory SUBSTEP history/provenance.
It reuses the package ``__version__`` -- NOT a second version source.

Config-as-data ONLY: the ordered entry list is an explicit curated list, NEVER a reflection/route/
DTO/exception scan. It carries no live/regulated/auth error models and no live error injection.
Distinct from the arch-repo docs summary (runtime build provenance, not a planning anchor).
READ-ONLY / advisory / mock-safe: NO balances, postings, payments, APY, uptime, latency, infra.
"""
from __future__ import annotations

from banxe_trading_backend import __version__
from banxe_trading_backend.models import CamelModel

# Config-as-data: curated, ordered advisory M1.x substep provenance. NOT a reflection/scan.
_ADVISORY_CHANGELOG: tuple[tuple[str, str], ...] = (
    ("M1.4", "earn advisory status taxonomy"),
    ("M1.5", "earn analytics/summary enrichment"),
    ("M1.6", "earn advisory statement"),
    ("M1.7", "accounts advisory metadata"),
    ("M1.8", "crypto asset catalogue"),
    ("M1.9", "instrument params (config-as-data)"),
    ("M1.10", "instruments list"),
    ("M1.11", "instrument-asset cross-reference"),
    ("M1.12", "markets bundle"),
    ("M1.13", "asset-to-markets reverse cross-reference"),
    ("M1.14", "catalogue meta (counts + version)"),
    ("M1.15", "earn taxonomy reference"),
    ("M1.16", "catalogue breakdown (asset-class)"),
    ("M1.17", "markets breakdown (per base/counter asset)"),
    ("M1.18", "instruments breakdown (schedule-ref/tick)"),
    ("M1.19", "symbols breakdown (status/precision)"),
    ("M1.20", "accounts breakdown (type/ledger-nature/status)"),
    ("M1.21", "network breakdown (flatten, dedup-per-entity)"),
    ("M1.22", "capability breakdown (flatten, dedup-per-entity)"),
    ("M1.23", "supported-asset breakdown (flatten, dedup-per-entity)"),
    ("M1.24", "advisory-surface manifest (endpoint inventory)"),
    ("M1.25", "schema inventory (DTO-family inventory)"),
    ("M1.26", "advisory-surface changelog (substep provenance)"),
)


class ChangelogEntry(CamelModel):
    """One advisory substep entry in the advisory-surface changelog (descriptive, read-only)."""

    substep: str
    title: str


class AdvisorySurfaceChangelog(CamelModel):
    """Read-only static config-as-data advisory-surface changelog (substep provenance; not a SoT).

    Ordered provenance of the advisory M1.x substeps published in this build (config-as-data, NOT a
    reflection/scan), reusing the package ``__version__``. Carries no live/regulated/auth error
    models; distinct from catalogue_meta / manifest / schema-inventory and from the docs summary.
    """

    entries: list[ChangelogEntry]
    total_entries: int
    version: str
    source: str


def advisory_surface_changelog() -> AdvisorySurfaceChangelog:
    """Build the advisory-surface changelog from the curated config (ordered; reuse version)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    entries = [ChangelogEntry(substep=s, title=t) for s, t in _ADVISORY_CHANGELOG]
    return AdvisorySurfaceChangelog(
        entries=entries,
        total_entries=len(entries),
        version=__version__,
        source=SANDBOX_MOCK,
    )
