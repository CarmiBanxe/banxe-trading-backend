"""Earn taxonomy reference / meta surface (M1.15, read-only descriptors).

Read-only REFERENCE layer over the existing earn controlled vocabularies: it enumerates the
``RiskBand`` and ``EarnAdvisoryStatus`` enums and a config-as-data lock-up tenor table, attaching
descriptive labels / ordering / lifecycle grouping. It is descriptive metadata ONLY -- a
descriptor view, NOT a second rates/analytics/status source-of-truth, NOT an executable state
machine.

It does NOT re-derive APY/yield (owned by ``earn/rates.py`` / ``/earn/rates``), compute fees
(``FeeEnginePort``), or surface balances/positions. Live-pipeline earn transaction states are
absent by construction (they are not members of ``EarnAdvisoryStatus``). READ-ONLY / advisory /
mock-safe; fail-closed -- an enum value without a configured descriptor is omitted, never faked.
"""
from __future__ import annotations

from banxe_trading_backend.earn.rates import RiskBand
from banxe_trading_backend.earn.status import EarnAdvisoryStatus
from banxe_trading_backend.models import CamelModel


class RiskBandDescriptor(CamelModel):
    """Descriptive reference for one earn risk band (advisory)."""

    code: str
    label: str
    ordering: int
    note: str


class AdvisoryStatusDescriptor(CamelModel):
    """Descriptive reference for one advisory earn lifecycle status."""

    code: str
    label: str
    phase: str


class LockupTenorDescriptor(CamelModel):
    """Descriptive lock-up tenor bucket (config-as-data; day bounds are meta, not money)."""

    code: str
    label: str
    min_days: int
    max_days: int | None


class EarnTaxonomy(CamelModel):
    """Read-only earn taxonomy reference (descriptor view; not a data source-of-truth)."""

    risk_bands: list[RiskBandDescriptor]
    advisory_statuses: list[AdvisoryStatusDescriptor]
    lockup_tenors: list[LockupTenorDescriptor]
    source: str


# config-as-data: descriptive labels/ordering over the existing RiskBand enum (no second band map).
_RISK_BAND_META: dict[RiskBand, tuple[str, int, str]] = {
    RiskBand.LOW: ("Low", 1, "Capital-preservation oriented; lowest advisory risk."),
    RiskBand.MEDIUM: ("Medium", 2, "Balanced advisory risk/return profile."),
    RiskBand.HIGH: ("High", 3, "Higher advisory risk; more variable outcomes."),
}

# config-as-data: lifecycle phase grouping for the existing EarnAdvisoryStatus enum (descriptive).
_STATUS_META: dict[EarnAdvisoryStatus, tuple[str, str]] = {
    EarnAdvisoryStatus.CREATED: ("Created", "active"),
    EarnAdvisoryStatus.INVESTING: ("Investing", "active"),
    EarnAdvisoryStatus.DEPOSITING: ("Depositing", "active"),
    EarnAdvisoryStatus.WITHDRAWING: ("Withdrawing", "active"),
    EarnAdvisoryStatus.NORMAL: ("Normal", "active"),
    EarnAdvisoryStatus.PROCESSING: ("Processing", "active"),
    EarnAdvisoryStatus.CLOSED: ("Closed", "terminal"),
    EarnAdvisoryStatus.COMPLETED: ("Completed", "terminal"),
    EarnAdvisoryStatus.NONE: ("None", "inactive"),
    EarnAdvisoryStatus.FAILED: ("Failed", "error"),
    EarnAdvisoryStatus.ERROR: ("Error", "error"),
}

# config-as-data: descriptive lock-up tenor buckets (day bounds are meta, not amounts).
_LOCKUP_TENORS: list[tuple[str, str, int, int | None]] = [
    ("flexible", "Flexible / no lock-up", 0, 0),
    ("short", "Short lock-up", 1, 30),
    ("medium", "Medium lock-up", 31, 90),
    ("locked", "Long lock-up", 91, None),
]


def earn_taxonomy() -> EarnTaxonomy:
    """Enumerate the earn taxonomy reference (fail-closed: skip enum values without config)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    bands = [
        RiskBandDescriptor(code=b.value, label=bm[0], ordering=bm[1], note=bm[2])
        for b in RiskBand
        if (bm := _RISK_BAND_META.get(b)) is not None
    ]
    bands.sort(key=lambda d: d.ordering)
    statuses = [
        AdvisoryStatusDescriptor(code=st.value, label=sm[0], phase=sm[1])
        for st in EarnAdvisoryStatus
        if (sm := _STATUS_META.get(st)) is not None
    ]
    tenors = [
        LockupTenorDescriptor(code=c, label=lbl, min_days=lo, max_days=hi)
        for (c, lbl, lo, hi) in _LOCKUP_TENORS
    ]
    return EarnTaxonomy(
        risk_bands=bands,
        advisory_statuses=statuses,
        lockup_tenors=tenors,
        source=SANDBOX_MOCK,
    )
