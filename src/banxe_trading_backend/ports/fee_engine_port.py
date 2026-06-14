"""Dynamic fee engine — advisory/analytics seam (Sprint S13 / X9.2), mock-safe.

Computes a fee ATTRIBUTION decomposition (integrator / builder-code / referral /
performance / maker-rebate / spread-capture) for a candidate action, as a
structured metadata response. STRICTLY advisory / analytics-only (ADR-090):
  * NO real charges, invoices, payments, or billing — this is metadata, not money;
  * NO Lago / Orb / Stripe, NO on-chain fee hooks, NO smart-contract changes;
  * mock-default, deterministic, no network, no keys; non-mock fails closed;
  * the response is unsigned/not-submitted (signed:false, submitted:false), like
    the S12 market-making preview.
It does NOT change billing, the /v1 BaaS facade, or any existing contract.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

from banxe_trading_backend.models import CamelModel, DecimalStr


class ProductType(str, Enum):
    SPOT = "spot"
    PERP = "perp"
    EARN = "earn"


# Mock fee schedule (bps by scheme × product type). NOT real rates — fixtures only.
_BASE_BPS: dict[str, dict[str, str]] = {
    "integrator_fee": {"spot": "25", "perp": "0", "earn": "0"},  # LI.FI-style integrator
    "builder_code_fee": {"spot": "0", "perp": "5", "earn": "0"},  # dYdX builder code
    "performance_fee": {"spot": "0", "perp": "0", "earn": "200"},  # StakeKit-style yield
    "bid_ask_spread_capture": {"spot": "8", "perp": "5", "earn": "0"},
}
_REFERRAL_BPS = "10"  # GMX-style referral, when a referralCode is present
_MAKER_REBATE_BPS = "-3"  # negative (paid to maker), when eligible
# Partner-tier discount on platform-take fees (not on rebate/spread). Mock.
_TIER_MULT: dict[str, str] = {"PRO": "0.8", "PLUS": "0.9"}


class FeePreviewRequest(CamelModel):
    venue: str
    route: str | None = None
    product_type: ProductType
    asset: str
    notional_usd: DecimalStr
    partner_tier: str | None = None
    integrator_id: str | None = None
    maker_rebate_eligible: bool = False
    referral_code: str | None = None


class FeeComponent(CamelModel):
    kind: str  # integrator_fee | builder_code_fee | referral_fee | performance_fee
    #          | maker_rebate | bid_ask_spread_capture
    bps: DecimalStr
    usd: DecimalStr
    source: str
    note: str | None = None


class FeePreviewResponse(CamelModel):
    mode: str
    signed: bool
    submitted: bool
    asset: str
    notional_usd: DecimalStr
    total_fee_bps: DecimalStr
    total_fee_usd: DecimalStr
    components: list[FeeComponent]
    disclaimer: str


@runtime_checkable
class FeeEnginePort(Protocol):
    """Advisory fee decomposition for a candidate action (no billing)."""

    def compute(self, request: FeePreviewRequest) -> list[FeeComponent]: ...


def _bps(d: Decimal) -> str:
    return str(d.quantize(Decimal("0.01")))


def _usd(notional: Decimal, bps: Decimal) -> str:
    return str((notional * bps / Decimal(10000)).quantize(Decimal("0.0001")))


class MockFeeEngine:
    """Deterministic mock fee attribution — fixtures only, no network/billing."""

    def compute(self, request: FeePreviewRequest) -> list[FeeComponent]:
        notional = Decimal(request.notional_usd)
        pt = request.product_type.value
        mult = (
            Decimal(_TIER_MULT.get(request.partner_tier, "1.0"))
            if request.partner_tier
            else Decimal("1")
        )
        components: list[FeeComponent] = []

        def add(kind: str, bps: Decimal, source: str, note: str | None = None) -> None:
            if bps == 0:
                return
            components.append(
                FeeComponent(
                    kind=kind, bps=_bps(bps), usd=_usd(notional, bps), source=source, note=note
                )
            )

        add("integrator_fee", Decimal(_BASE_BPS["integrator_fee"][pt]) * mult, "LI.FI-mock")
        add(
            "builder_code_fee",
            Decimal(_BASE_BPS["builder_code_fee"][pt]) * mult,
            "dYdX-builder-mock",
        )
        if request.referral_code:
            add(
                "referral_fee",
                Decimal(_REFERRAL_BPS) * mult,
                "GMX-mock",
                note=f"referral {request.referral_code}",
            )
        add("performance_fee", Decimal(_BASE_BPS["performance_fee"][pt]) * mult, "StakeKit-mock")
        if request.maker_rebate_eligible:
            add("maker_rebate", Decimal(_MAKER_REBATE_BPS), "MM-rebate-mock")  # no tier; negative
        add(
            "bid_ask_spread_capture",
            Decimal(_BASE_BPS["bid_ask_spread_capture"][pt]),
            "spread-mock",
        )
        return components


def build_fee_provider(name: str) -> FeeEnginePort:
    """Resolve a fee engine by name. Only 'mock' is wired (default)."""
    if name == "mock":
        return MockFeeEngine()
    # A live fee/attribution source (or any billing integration) is OPERATOR-GATED.
    raise ValueError(
        f"fee engine provider {name!r} is not wired (operator-gated); only 'mock'"
    )
