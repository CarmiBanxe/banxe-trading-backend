"""Advisory account/wallet metadata (M1.7, read-only, config-as-data).

Descriptive-only account metadata: account types, ledger nature, statuses, supported assets,
and capability flags -- traced from legacy descriptive enums (vabs2 account-type /
ledger-account-type, wallester account-status, supported-fiat tickers). It is a NEW additive
read-only view; it does NOT model balances/postings/transfers and makes NO Midaz LedgerPort
calls. The canonical live account/ledger source-of-truth is the Midaz LedgerPort (ADR-013),
which this module wraps DESCRIPTIVELY only -- never its live operations.

READ-ONLY / advisory / mock-safe: NO balances, NO postings, NO amounts, NO money movement.
Config-as-data; fail-closed (skip malformed entries; never a fake value).
"""
from __future__ import annotations

from banxe_trading_backend.models import CamelModel

# Descriptive vocabularies (legacy: vabs2 account-type / ledger-account-type, wallester status).
_ACCOUNT_TYPES: tuple[str, ...] = ("INTERNAL", "EXTERNAL", "SYSTEM")
_LEDGER_NATURES: tuple[str, ...] = ("ACTIVE", "PASSIVE")
_ACCOUNT_STATUSES: tuple[str, ...] = ("ACTIVE", "CLOSED", "CLOSING")
_SUPPORTED_FIAT: tuple[str, ...] = ("EUR", "GBP", "USD", "CHF")
_SUPPORTED_CRYPTO: tuple[str, ...] = ("BTC", "ETH", "USDC")

# Config-as-data: static advisory account-metadata catalogue (descriptive; NO balances).
_ACCOUNT_METADATA: tuple[dict[str, object], ...] = (
    {
        "account_type": "INTERNAL", "ledger_nature": "ACTIVE", "account_status": "ACTIVE",
        "supported_assets": [*_SUPPORTED_FIAT, *_SUPPORTED_CRYPTO],
        "capabilities": ["fiat", "crypto", "self_custodial"],
    },
    {
        "account_type": "EXTERNAL", "ledger_nature": "PASSIVE", "account_status": "ACTIVE",
        "supported_assets": list(_SUPPORTED_FIAT),
        "capabilities": ["fiat"],
    },
    {
        "account_type": "SYSTEM", "ledger_nature": "ACTIVE", "account_status": "ACTIVE",
        "supported_assets": [],
        "capabilities": ["internal"],
    },
)

_DISCLAIMER = (
    "Advisory read-only account metadata (sandbox-mock): descriptive account types / "
    "capabilities only -- NO balances, postings, transfers, or live ledger operations. "
    "Canonical account/ledger source-of-truth is the Midaz LedgerPort (ADR-013)."
)


class AccountAdvisoryMetadata(CamelModel):
    """Descriptive advisory account metadata (read-only; not a live account/balance)."""

    account_type: str
    ledger_nature: str
    account_status: str
    supported_assets: list[str]
    capabilities: list[str]
    source: str


class AccountMetadataResponse(CamelModel):
    """Read-only advisory account metadata set (sandbox-mock, config-as-data)."""

    accounts: list[AccountAdvisoryMetadata]
    source: str
    disclaimer: str


def _str_list(value: object) -> list[str]:
    return [str(x) for x in value] if isinstance(value, list) else []


def account_metadata(
    config: tuple[dict[str, object], ...] | None = None,
) -> AccountMetadataResponse:
    """Assemble read-only advisory account metadata from config-as-data (fail-closed)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    source_cfg = config if config is not None else _ACCOUNT_METADATA
    entries: list[AccountAdvisoryMetadata] = []
    for cfg in source_cfg:
        try:
            atype = str(cfg.get("account_type", ""))
            nature = str(cfg.get("ledger_nature", ""))
            status = str(cfg.get("account_status", ""))
            if (
                atype not in _ACCOUNT_TYPES
                or nature not in _LEDGER_NATURES
                or status not in _ACCOUNT_STATUSES
            ):
                continue  # fail-closed: skip malformed/unsupported config (no fake value)
            entries.append(
                AccountAdvisoryMetadata(
                    account_type=atype,
                    ledger_nature=nature,
                    account_status=status,
                    supported_assets=_str_list(cfg.get("supported_assets")),
                    capabilities=_str_list(cfg.get("capabilities")),
                    source=SANDBOX_MOCK,
                )
            )
        except Exception:
            continue  # fail-closed: never emit a fake/partial entry
    return AccountMetadataResponse(accounts=entries, source=SANDBOX_MOCK, disclaimer=_DISCLAIMER)
