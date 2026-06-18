"""Advisory crypto asset catalogue metadata (M1.8, read-only, config-as-data).

Descriptive per-asset metadata catalogue. The asset UNIVERSE is reused from the canonical
trading symbol seam (``MarketDataPort.list_symbols()`` / ``SymbolInfo`` base/quote assets) and
enriched with config-as-data descriptors (name, asset_class, networks, display_decimals). It is
a NEW additive read-only view; ``SymbolInfo`` / ``InstrumentInfo`` / ``MarketDataPort`` remain
the frozen symbol/instrument source-of-truth (reused, NOT duplicated) -- no second symbol model.

READ-ONLY / advisory / mock-safe: NO balances, transactions, wallet operations, deposits,
withdrawals, transfers, payments, or account-ownership semantics. Config-as-data; fail-closed
(skip malformed; empty when the symbol universe is unavailable -- never a fake value).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from banxe_trading_backend.models import CamelModel

if TYPE_CHECKING:  # runtime-import-free: avoid an import cycle; only the duck-typed call is used
    from banxe_trading_backend.ports import MarketDataPort

# config-as-data: descriptive per-asset metadata (NOT balances/amounts).
_ASSET_META: dict[str, dict[str, object]] = {
    "BTC": {
        "name": "Bitcoin", "asset_class": "crypto",
        "networks": ["bitcoin"], "display_decimals": 8,
    },
    "ETH": {
        "name": "Ethereum", "asset_class": "crypto",
        "networks": ["ethereum"], "display_decimals": 18,
    },
    "USDC": {
        "name": "USD Coin", "asset_class": "stablecoin",
        "networks": ["ethereum"], "display_decimals": 6,
    },
    "USDT": {
        "name": "Tether USD", "asset_class": "stablecoin",
        "networks": ["ethereum"], "display_decimals": 6,
    },
    "EUR": {
        "name": "Euro", "asset_class": "fiat",
        "networks": [], "display_decimals": 2,
    },
    "GBP": {
        "name": "Pound Sterling", "asset_class": "fiat",
        "networks": [], "display_decimals": 2,
    },
    "USD": {
        "name": "US Dollar", "asset_class": "fiat",
        "networks": [], "display_decimals": 2,
    },
}
_DEFAULT_META: dict[str, object] = {
    "name": "", "asset_class": "crypto", "networks": [], "display_decimals": 8,
}

_DISCLAIMER = (
    "Advisory read-only crypto asset metadata (sandbox-mock): descriptive catalogue only -- "
    "NO balances, transactions, wallet operations, or fund movement."
)


class CryptoAssetMetadata(CamelModel):
    """Descriptive advisory metadata for one asset (read-only; not a wallet/balance)."""

    asset: str
    name: str
    asset_class: str
    networks: list[str]
    display_decimals: int
    source: str


class AssetCatalogResponse(CamelModel):
    """Read-only advisory crypto asset catalogue (sandbox-mock, config-as-data)."""

    assets: list[CryptoAssetMetadata]
    source: str
    disclaimer: str


def _asset_universe(market_data: MarketDataPort) -> list[str]:
    """Deterministic, deduplicated asset universe from the symbol catalogue (fail-closed)."""
    seen: list[str] = []
    try:
        symbols = market_data.list_symbols()
    except Exception:
        return []  # fail-closed: no market-data -> empty universe (never fabricated)
    for sym in symbols:
        for asset in (getattr(sym, "base_asset", None), getattr(sym, "quote_asset", None)):
            if isinstance(asset, str) and asset and asset not in seen:
                seen.append(asset)
    return sorted(seen)


def asset_catalog(market_data: MarketDataPort) -> AssetCatalogResponse:
    """Assemble the read-only advisory asset catalogue (fail-closed; descriptive only)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    assets: list[CryptoAssetMetadata] = []
    for asset in _asset_universe(market_data):
        meta = _ASSET_META.get(asset, _DEFAULT_META)
        try:
            raw_networks = meta.get("networks", [])
            networks = [str(n) for n in raw_networks] if isinstance(raw_networks, list) else []
            raw_dd = meta.get("display_decimals", 8)
            display_decimals = raw_dd if isinstance(raw_dd, int) else 8
            assets.append(
                CryptoAssetMetadata(
                    asset=asset,
                    name=str(meta.get("name") or asset),
                    asset_class=str(meta.get("asset_class", "crypto")),
                    networks=networks,
                    display_decimals=display_decimals,
                    source=SANDBOX_MOCK,
                )
            )
        except Exception:
            continue  # fail-closed: skip malformed config (no fake/partial entry)
    return AssetCatalogResponse(assets=assets, source=SANDBOX_MOCK, disclaimer=_DISCLAIMER)



def asset_metadata(asset: str) -> CryptoAssetMetadata:
    """Advisory CryptoAssetMetadata for one asset (reuses _ASSET_META; deterministic default).

    Single-asset accessor over the existing M1.8 source -- no second asset map/catalogue. Falls
    back to the established generic descriptor for an unconfigured asset (descriptive, not a
    fabricated balance/price). Read-only / advisory.
    """
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    key = (asset or "").upper()
    meta = _ASSET_META.get(key, _DEFAULT_META)
    raw_networks = meta.get("networks", [])
    networks = [str(n) for n in raw_networks] if isinstance(raw_networks, list) else []
    raw_dd = meta.get("display_decimals", 8)
    display_decimals = raw_dd if isinstance(raw_dd, int) else 8
    return CryptoAssetMetadata(
        asset=key,
        name=str(meta.get("name") or key),
        asset_class=str(meta.get("asset_class", "crypto")),
        networks=networks,
        display_decimals=display_decimals,
        source=SANDBOX_MOCK,
    )
