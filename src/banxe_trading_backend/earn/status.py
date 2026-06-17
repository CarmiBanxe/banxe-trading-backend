"""Advisory earn lifecycle status taxonomy (M1.4) — single EMI source-of-truth.

Read-only ADVISORY descriptive taxonomy of the legacy ``banxe-crypto-earn`` position /
operation lifecycle, traced 1:1 from the legacy enums (M1.4 deep-read):
``earn-status`` (product/position), ``position-status``, and ``operation-status``.

It is descriptive metadata ONLY — NOT an executable state machine, NOT the live
transaction pipeline. The legacy live-pipeline transaction states
(DRAFT/FIAT_SENDING/EXCHANGING/FEE_SENDING/MAIN_SENDING/CRYPTO_EARN_SENDING/
WITHDRAW_TRANSACTION_AWAITING) describe live invest/withdraw execution and are
**deliberately NOT modelled here** (operator-gated, out-of-scope) — ``from_legacy``
fail-closes on them.

This is the ONLY EMI source-of-truth for earn status. The adjacent EMI enums
``OrderState`` (trading orders), ``RiskBand`` (earn risk band) and the marketplace
catalog ``status`` (listing maturity) are DISTINCT domains and are NOT reused here.
"""

from __future__ import annotations

from enum import Enum


class EarnAdvisoryStatus(str, Enum):
    """Advisory earn position/operation lifecycle status (descriptive; not a state machine).

    Deduplicated union of the externally-meaningful legacy lifecycle states. Advisory only —
    not a promise of return, not an execution signal.
    """

    # product/position lifecycle (legacy earn-status + position-status)
    CREATED = "CREATED"
    INVESTING = "INVESTING"
    DEPOSITING = "DEPOSITING"
    WITHDRAWING = "WITHDRAWING"
    NORMAL = "NORMAL"
    CLOSED = "CLOSED"
    FAILED = "FAILED"
    NONE = "NONE"
    # operation outcome (legacy operation-status)
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


# Legacy status string -> advisory status. Lists ONLY the supported advisory states; legacy
# live-pipeline transaction states are intentionally absent => from_legacy fail-closes on them.
_LEGACY_ADVISORY: frozenset[str] = frozenset(s.value for s in EarnAdvisoryStatus)


def from_legacy(value: str) -> EarnAdvisoryStatus:
    """Map a legacy earn status string to the advisory taxonomy (fail-closed).

    Raises ``ValueError`` for unsupported / live-pipeline-only / non-wired statuses, so the
    advisory surface never silently invents or executes a non-advisory state.
    """
    key = (value or "").strip().upper()
    if key not in _LEGACY_ADVISORY:
        raise ValueError(
            f"unsupported earn status {value!r} (advisory taxonomy is descriptive-only; "
            "live transaction-pipeline states are operator-gated, out-of-scope)"
        )
    return EarnAdvisoryStatus(key)
