"""Quant-moat advisory seam (Sprint S14 / X9.3) — quant-analytics port, mock-only.

An OPTIONAL analytics seam that emits quant signals (fair-value gap, stress
scenario, volatility regime, flash-crash / inventory flags) as ADVISORY metadata
to enrich the DSE / preview / fees / mm flows. STRICTLY mock-safe (ADR-091):
  * NO live quant engine — no Heston / rough-Heston / Remizov / FNO / PINN / deep
    hedging; only light deterministic logic + fixtures (we emulate signal SHAPE);
  * NO live price feeds, NO keys, NO network, NO on-chain execution;
  * mock-default; non-mock fails closed; mode is always "sandbox-mock";
  * the signals are ADDITIVE metadata, never a critical input — CORE endpoints
    work unchanged if no quant provider is present.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

from banxe_trading_backend.models import CamelModel, DecimalStr


class QuantProductType(str, Enum):
    SPOT = "spot"
    PERP = "perp"
    EARN = "earn"
    OPTION = "option"


# Mock reference prices + regime by asset base (fixtures only; not live).
_REF_PRICE: dict[str, str] = {
    "BTC": "67250", "ETH": "2000", "SOL": "150", "USDC": "1", "USDT": "1", "DAI": "1",
}
_LOW_VOL = {"USDC", "USDT", "DAI"}
_HIGH_VOL = {"BTC", "ETH"}
_REGIME_GAP_BPS = {"low": "10", "medium": "40", "high": "75"}
_REGIME_STRESS_PCT = {"low": "-2", "medium": "-8", "high": "-15"}
_REGIME_SCORE = {"low": "0.20", "medium": "0.50", "high": "0.80"}


class QuantPreviewRequest(CamelModel):
    asset: str
    product_type: QuantProductType
    notional_usd: DecimalStr
    venue: str | None = None
    horizon_days: int = 7
    risk_profile: str | None = None
    implied_vol: DecimalStr | None = None
    current_spread_bps: DecimalStr | None = None


class QuantSignal(CamelModel):
    kind: str  # fair_value_gap | stress_scenario_score | flash_crash_guard
    #          | inventory_risk_flag | volatility_regime
    score: DecimalStr  # deterministic, in [-1, 1]
    label: str
    note: str | None = None


class QuantPreviewResponse(CamelModel):
    mode: str
    asset: str
    product_type: str
    notional_usd: DecimalStr
    fair_value_usd: DecimalStr | None = None
    fair_value_gap_bps: DecimalStr | None = None
    stress_pnl_downside_pct: DecimalStr | None = None
    volatility_regime: str | None = None
    signals: list[QuantSignal]
    disclaimer: str


@runtime_checkable
class QuantEnginePort(Protocol):
    """Advisory quant analytics for a candidate action (no live models)."""

    def compute(self, request: QuantPreviewRequest) -> QuantPreviewResponse: ...


_DISCLAIMER = (
    "Sandbox-only quant PREVIEW — advisory mock signals (no live models: no Heston "
    "/ rough-Heston / Remizov / FNO / deep hedging). No live price feeds, no keys, "
    "no trading decisions; deterministic fixtures. Additive metadata only."
)


def _base_asset(asset: str) -> str:
    upper = asset.upper()
    for key in sorted(_REF_PRICE, key=len, reverse=True):
        if upper == key or upper.startswith(key):
            return key
    return upper


def _regime(base: str) -> str:
    if base in _LOW_VOL:
        return "low"
    if base in _HIGH_VOL:
        return "high"
    return "medium"


def _clamp(d: Decimal) -> Decimal:
    return max(Decimal("-1"), min(Decimal("1"), d)).quantize(Decimal("0.01"))


class MockQuantEngine:
    """Deterministic mock quant signals — fixtures only, no network/live models."""

    def compute(self, request: QuantPreviewRequest) -> QuantPreviewResponse:
        base = _base_asset(request.asset)
        regime = _regime(base)
        ref = Decimal(_REF_PRICE.get(base, "100"))
        # Deterministic signed gap: magnitude by regime, sign by asset+product hash.
        digest = hashlib.sha256(f"{base}|{request.product_type.value}".encode()).hexdigest()
        sign = Decimal(1) if int(digest[:8], 16) % 2 == 0 else Decimal(-1)
        gap_bps = (sign * Decimal(_REGIME_GAP_BPS[regime])).quantize(Decimal("0.01"))
        fair_value = (ref * (Decimal(1) + gap_bps / Decimal(10000))).quantize(Decimal("0.01"))
        # Downside stress scales lightly with the horizon (deterministic, bounded).
        horizon_factor = Decimal(1) + Decimal(request.horizon_days - 7) * Decimal("0.01")
        stress = (Decimal(_REGIME_STRESS_PCT[regime]) * horizon_factor).quantize(Decimal("0.01"))

        signals: list[QuantSignal] = [
            QuantSignal(
                kind="fair_value_gap",
                score=str(_clamp(gap_bps / Decimal(100))),
                label=(
                    "Overvalued vs mock fair value"
                    if gap_bps < 0
                    else "Undervalued vs mock fair value"
                ),
                note="Mock Remizov-style fair value gap",
            ),
            QuantSignal(
                kind="stress_scenario_score",
                score=str(_clamp(stress / Decimal(25))),
                label=f"{request.horizon_days}d downside stress",
                note="Mock scenario engine",
            ),
            QuantSignal(
                kind="volatility_regime",
                score=_REGIME_SCORE[regime],
                label=f"Volatility regime: {regime}",
            ),
        ]
        if regime == "high" and stress < Decimal("-10"):
            signals.append(
                QuantSignal(
                    kind="flash_crash_guard", score="0.80", label="Elevated flash-crash risk"
                )
            )
        if request.product_type is QuantProductType.PERP and regime == "high":
            signals.append(
                QuantSignal(
                    kind="inventory_risk_flag", score="0.60", label="Inventory risk elevated"
                )
            )

        return QuantPreviewResponse(
            mode="sandbox-mock",
            asset=request.asset,
            product_type=request.product_type.value,
            notional_usd=request.notional_usd,
            fair_value_usd=str(fair_value),
            fair_value_gap_bps=str(gap_bps),
            stress_pnl_downside_pct=str(stress),
            volatility_regime=regime,
            signals=signals,
            disclaimer=_DISCLAIMER,
        )


def build_quant_provider(name: str) -> QuantEnginePort:
    """Resolve a quant engine by name. Only 'mock' is wired (default)."""
    if name == "mock":
        return MockQuantEngine()
    # A live quant stack (Remizov / Heston / FNO / ...) is OPERATOR-GATED (ODR).
    raise ValueError(
        f"quant engine provider {name!r} is not wired (operator-gated); only 'mock'"
    )
