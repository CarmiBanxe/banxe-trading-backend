"""Legacy crypto-earn → advisory earn-rates provider variant (M1.2, mock-safe).

Surfaces the legacy ``banxe-crypto-earn`` product/fee structure as ADVISORY
``EarnMetrics`` behind the EXISTING ``EarnRatesProvider`` seam — it **extends** the
seam (a new selectable provider), it does NOT replace ``MockEarnRatesProvider`` or
change the ``EarnMetrics`` contract.

The legacy module stored money as ``BigNumber`` (bignumber.js) over DB ``decimal``
(see M1.1 deep-read); here every value is normalized to ``DecimalStr`` (I-01) via
``normalize_decimal`` — the BigNumber→Decimal path. The full legacy earn-config fee
structure (minimal amount, investment fee %, minimal investment fee USDT, withdrawal
fee USDT, crypto-earn withdrawal fee %, quickswap fee %) plus the legacy product risk
level (``RiskLevelEnum``: MINIMAL/LOW/MEDIUM/HIGH) and TVL are surfaced in
``risk_summary``. (M1.3 added minimal-investment-fee-USDT, absolute withdrawal-fee-USDT,
risk-level and TVL, traced to src/earn-config/earn-config.entity.ts and
src/crypto-earn-api/interfaces/product.interface.ts in the snapshot.)
Yields/fees are **deterministic MOCK** values (advisory only, not a
promise of return). NO network, NO keys, NO execution; the legacy live couplings
(FastExchange / ABS / RabbitMQ) are out-of-scope and operator-gated.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from banxe_trading_backend.dse.models import EarnMetrics

_PLACES = Decimal("0.0001")

# Legacy product risk levels (src/crypto-earn-api/enums/risk-level.enum.ts).
LEGACY_RISK_LEVELS: tuple[str, ...] = ("MINIMAL", "LOW", "MEDIUM", "HIGH")


def normalize_decimal(value: str | int | float) -> str:
    """Normalize a legacy BigNumber-style value to a canonical 4dp DecimalStr (I-01).

    Fail-closed: a non-numeric value raises ``ValueError`` rather than coercing.
    """
    try:
        normalized = Decimal(str(value)).quantize(_PLACES)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid earn decimal value: {value!r}") from exc
    return str(normalized)


# Legacy crypto-earn product/fee structure (field shape from the M1.1 deep-read;
# the numbers are deterministic MOCK fixtures — advisory only, not real DB data).
_LEGACY_EARN_BY_BASE: dict[str, dict[str, object]] = {
    "USDC": {
        "yield": "5.0000", "investment_fee_pct": "0.5000", "withdrawal_fee_pct": "0.2500",
        "quickswap_fee_pct": "0.1000", "min_usdt": "10", "min_investment_fee_usdt": "1",
        "withdrawal_fee_usdt": "2", "risk_level": "LOW", "tvl": "1500000",
        "protocol": "mock-crypto-earn-lending", "lockup": 0,
    },
    "BTC": {
        "yield": "3.2000", "investment_fee_pct": "0.7500", "withdrawal_fee_pct": "0.3000",
        "quickswap_fee_pct": "0.1500", "min_usdt": "25", "min_investment_fee_usdt": "5",
        "withdrawal_fee_usdt": "8", "risk_level": "MEDIUM", "tvl": "8000000",
        "protocol": "mock-crypto-earn-staking", "lockup": 7,
    },
    "ETH": {
        "yield": "4.0000", "investment_fee_pct": "0.6000", "withdrawal_fee_pct": "0.2500",
        "quickswap_fee_pct": "0.1200", "min_usdt": "20", "min_investment_fee_usdt": "3",
        "withdrawal_fee_usdt": "5", "risk_level": "MEDIUM", "tvl": "5000000",
        "protocol": "mock-crypto-earn-staking", "lockup": 0,
    },
}
_DEFAULT_EARN: dict[str, object] = {
    "yield": "2.0000", "investment_fee_pct": "1.0000", "withdrawal_fee_pct": "0.5000",
    "quickswap_fee_pct": "0.2000", "min_usdt": "50", "min_investment_fee_usdt": "5",
    "withdrawal_fee_usdt": "5", "risk_level": "HIGH", "tvl": "100000",
    "protocol": "mock-crypto-earn-generic", "lockup": 0,
}


def _fee_note(cfg: dict[str, object]) -> str:
    return (
        "Legacy crypto-earn fees (advisory, mock): investment "
        f"{normalize_decimal(str(cfg['investment_fee_pct']))}% (min "
        f"{normalize_decimal(str(cfg['min_investment_fee_usdt']))} USDT), withdrawal "
        f"{normalize_decimal(str(cfg['withdrawal_fee_pct']))}% / "
        f"{normalize_decimal(str(cfg['withdrawal_fee_usdt']))} USDT, quickswap "
        f"{normalize_decimal(str(cfg['quickswap_fee_pct']))}%, min entry "
        f"{normalize_decimal(str(cfg['min_usdt']))} USDT; risk level "
        f"{cfg['risk_level']}, TVL {normalize_decimal(str(cfg['tvl']))} USDT. Estimate "
        "only, NOT a promise of return; live invest/withdraw out-of-scope (operator-gated)."
    )


class CryptoEarnRatesProvider:
    """Legacy-derived advisory earn rates (mock-safe). Implements ``EarnRatesProvider``."""

    async def get_earn_metrics(self, asset: str) -> EarnMetrics:
        cfg = self._lookup(asset)
        return EarnMetrics(
            current_yield_pct=normalize_decimal(str(cfg["yield"])),
            protocol=str(cfg["protocol"]),
            chain="ethereum",
            lockup_days=int(cfg["lockup"]),  # type: ignore[call-overload]
            variable_rate=True,
            risk_summary=_fee_note(cfg),
        )

    @staticmethod
    def _lookup(asset: str) -> dict[str, object]:
        upper = asset.upper()
        for base, cfg in _LEGACY_EARN_BY_BASE.items():
            if upper.startswith(base):
                return cfg
        return _DEFAULT_EARN
