"""Legacy crypto-earn → advisory earn-rates provider variant (M1.2, mock-safe).

Surfaces the legacy ``banxe-crypto-earn`` product/fee structure as ADVISORY
``EarnMetrics`` behind the EXISTING ``EarnRatesProvider`` seam — it **extends** the
seam (a new selectable provider), it does NOT replace ``MockEarnRatesProvider`` or
change the ``EarnMetrics`` contract.

The legacy module stored money as ``BigNumber`` (bignumber.js) over DB ``decimal``
(see M1.1 deep-read); here every value is normalized to ``DecimalStr`` (I-01) via
``normalize_decimal`` — the BigNumber→Decimal path. The legacy earn-config fee
structure (investment / withdrawal / quickswap fees, minimal amount) is surfaced in
``risk_summary``. Yields/fees are **deterministic MOCK** values (advisory only, not a
promise of return). NO network, NO keys, NO execution; the legacy live couplings
(FastExchange / ABS / RabbitMQ) are out-of-scope and operator-gated.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from banxe_trading_backend.dse.models import EarnMetrics

_PLACES = Decimal("0.0001")


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
        "quickswap_fee_pct": "0.1000", "min_usdt": "10",
        "protocol": "mock-crypto-earn-lending", "lockup": 0,
    },
    "BTC": {
        "yield": "3.2000", "investment_fee_pct": "0.7500", "withdrawal_fee_pct": "0.3000",
        "quickswap_fee_pct": "0.1500", "min_usdt": "25",
        "protocol": "mock-crypto-earn-staking", "lockup": 7,
    },
    "ETH": {
        "yield": "4.0000", "investment_fee_pct": "0.6000", "withdrawal_fee_pct": "0.2500",
        "quickswap_fee_pct": "0.1200", "min_usdt": "20",
        "protocol": "mock-crypto-earn-staking", "lockup": 0,
    },
}
_DEFAULT_EARN: dict[str, object] = {
    "yield": "2.0000", "investment_fee_pct": "1.0000", "withdrawal_fee_pct": "0.5000",
    "quickswap_fee_pct": "0.2000", "min_usdt": "50", "protocol": "mock-crypto-earn-generic",
    "lockup": 0,
}


def _fee_note(cfg: dict[str, object]) -> str:
    return (
        "Legacy crypto-earn fees (advisory, mock): investment "
        f"{normalize_decimal(str(cfg['investment_fee_pct']))}%, withdrawal "
        f"{normalize_decimal(str(cfg['withdrawal_fee_pct']))}%, quickswap "
        f"{normalize_decimal(str(cfg['quickswap_fee_pct']))}%, min "
        f"{normalize_decimal(str(cfg['min_usdt']))} USDT. Estimate only, NOT a promise "
        "of return; live invest/withdraw out-of-scope (operator-gated)."
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
