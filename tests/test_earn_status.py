"""M1.4 — advisory earn status taxonomy tests (mock-safe, no execution).

characterization: legacy -> EMI advisory mapping; contract: frozen EarnMetrics + earn
exports preserved; negative: fail-closed on unsupported / live-pipeline-only statuses.
"""
from __future__ import annotations

import pytest

from banxe_trading_backend.dse.models import EarnMetrics
from banxe_trading_backend.earn import EarnAdvisoryStatus, from_legacy

# ---- characterization: legacy semantics -> advisory taxonomy --------------------

@pytest.mark.parametrize(
    "legacy",
    ["CREATED", "INVESTING", "DEPOSITING", "WITHDRAWING", "NORMAL", "CLOSED",
     "FAILED", "NONE", "PROCESSING", "COMPLETED", "ERROR"],
)
def test_from_legacy_maps_supported_advisory_states(legacy: str) -> None:
    status = from_legacy(legacy)
    assert isinstance(status, EarnAdvisoryStatus)
    assert status.value == legacy


def test_from_legacy_is_case_insensitive() -> None:
    assert from_legacy("investing") is EarnAdvisoryStatus.INVESTING


def test_taxonomy_is_str_enum_and_traces_legacy_union() -> None:
    # str-Enum (wire-safe DecimalStr-style discipline: plain string values)
    assert issubclass(EarnAdvisoryStatus, str)
    assert {s.value for s in EarnAdvisoryStatus} == {
        "CREATED", "INVESTING", "DEPOSITING", "WITHDRAWING", "NORMAL", "CLOSED",
        "FAILED", "NONE", "PROCESSING", "COMPLETED", "ERROR",
    }


# ---- contract: frozen consumers unaffected --------------------------------------

def test_earnmetrics_contract_unchanged() -> None:
    """EarnMetrics keeps exactly its frozen field set — no status field added."""
    assert set(EarnMetrics.model_fields.keys()) == {
        "current_yield_pct", "protocol", "chain", "lockup_days",
        "variable_rate", "risk_summary",
    }


def test_earn_package_exports_preserved_and_additive() -> None:
    import banxe_trading_backend.earn as earn
    # existing seam exports still present
    for sym in ("EarnRatesProvider", "MockEarnRatesProvider", "build_earn_provider",
                "RateCard", "RiskBand", "earn_rates"):
        assert hasattr(earn, sym)
    # new advisory symbols added (additive)
    assert hasattr(earn, "EarnAdvisoryStatus") and hasattr(earn, "from_legacy")


# ---- negative: fail-closed ------------------------------------------------------

@pytest.mark.parametrize(
    "live_or_unsupported",
    ["FIAT_SENDING", "EXCHANGING", "FEE_SENDING", "MAIN_SENDING",
     "CRYPTO_EARN_SENDING", "WITHDRAW_TRANSACTION_AWAITING", "DRAFT",  # live-pipeline
     "BOGUS", "", "   "],                                              # unsupported / empty
)
def test_from_legacy_fails_closed(live_or_unsupported: str) -> None:
    with pytest.raises(ValueError, match="unsupported earn status|operator-gated"):
        from_legacy(live_or_unsupported)
