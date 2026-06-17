"""M1.2 — characterization + contract tests for the legacy crypto-earn provider variant.

Verifies the new ``CryptoEarnRatesProvider`` (a) normalizes legacy BigNumber-style
values to DecimalStr, (b) satisfies the existing ``EarnRatesProvider`` Protocol without
changing the ``EarnMetrics`` contract, (c) is deterministic + offline, and (d) the seam
stays fail-closed for non-wired names. NO live coupling is exercised.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from banxe_trading_backend.dse.models import EarnMetrics
from banxe_trading_backend.earn.crypto_earn import (
    CryptoEarnRatesProvider,
    normalize_decimal,
)
from banxe_trading_backend.earn.providers import (
    EarnRatesProvider,
    MockEarnRatesProvider,
    build_earn_provider,
)

# ---- characterization: BigNumber -> DecimalStr (I-01) ----------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("4.2", "4.2000"),
        (5, "5.0000"),
        ("0.5", "0.5000"),
        ("3.14159", "3.1416"),  # quantize to 4dp (ROUND_HALF_EVEN)
        ("0", "0.0000"),
    ],
)
def test_normalize_decimal_canonical(raw: object, expected: str) -> None:
    assert normalize_decimal(raw) == expected  # type: ignore[arg-type]


def test_normalize_decimal_fails_closed_on_garbage() -> None:
    with pytest.raises(ValueError, match="invalid earn decimal value"):
        normalize_decimal("not-a-number")


# ---- contract: satisfies EarnRatesProvider, EarnMetrics unchanged ---------------

def test_provider_satisfies_protocol() -> None:
    assert isinstance(CryptoEarnRatesProvider(), EarnRatesProvider)


def test_get_earn_metrics_returns_valid_metrics() -> None:
    em = asyncio.run(CryptoEarnRatesProvider().get_earn_metrics("USDC"))
    assert isinstance(em, EarnMetrics)
    assert Decimal(em.current_yield_pct) > 0  # DecimalStr parses
    assert em.protocol.startswith("mock-crypto-earn")
    assert "advisory" in em.risk_summary.lower()
    assert "investment" in em.risk_summary.lower()  # legacy fee structure surfaced


def test_deterministic() -> None:
    a = asyncio.run(CryptoEarnRatesProvider().get_earn_metrics("BTCUSDT"))
    b = asyncio.run(CryptoEarnRatesProvider().get_earn_metrics("BTCUSDT"))
    assert a.model_dump() == b.model_dump()


def test_unknown_asset_falls_back_to_default() -> None:
    em = asyncio.run(CryptoEarnRatesProvider().get_earn_metrics("XRP"))
    assert em.protocol == "mock-crypto-earn-generic"
    assert Decimal(em.current_yield_pct) >= 0


# ---- seam: additive + fail-closed -----------------------------------------------

def test_seam_wires_crypto_earn() -> None:
    assert isinstance(build_earn_provider("crypto-earn"), CryptoEarnRatesProvider)


def test_seam_mock_unchanged() -> None:
    assert isinstance(build_earn_provider("mock"), MockEarnRatesProvider)


def test_seam_fails_closed_on_nonwired() -> None:
    with pytest.raises(ValueError, match="operator-gated"):
        build_earn_provider("crypto-earn-live")
