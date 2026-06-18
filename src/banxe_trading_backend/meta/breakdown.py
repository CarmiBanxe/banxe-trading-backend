"""Public read-only catalogue breakdown (M1.16, derived per-asset-class counts).

Derives the per-``asset_class`` cardinalities (crypto / stablecoin / fiat) of the advisory asset
catalogue by grouping ``asset_catalog(market_data).assets`` on ``CryptoAssetMetadata.asset_class``.
A DERIVED summary over the existing asset catalogue -- NOT a second registry, counter store,
version source, or asset map; it does NOT mutate the frozen ``CatalogueMeta``.

READ-ONLY / advisory / mock-safe: integer meta counts ONLY -- NO balances, amounts, APY/rates,
fees, execution, or payments. Counts inherit the fail-closed ``asset_catalog`` (malformed entries
already skipped upstream); never a fabricated count or class.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from banxe_trading_backend.accounts.metadata import account_metadata
from banxe_trading_backend.assets.catalog import asset_catalog
from banxe_trading_backend.instruments.params import list_instruments
from banxe_trading_backend.instruments.xref import list_instrument_asset_xref
from banxe_trading_backend.models import CamelModel

if TYPE_CHECKING:
    from banxe_trading_backend.ports import MarketDataPort

# deterministic display ordering: canonical classes first, any extras appended sorted.
_CLASS_ORDER = ("crypto", "stablecoin", "fiat")


class AssetClassCount(CamelModel):
    """Count of catalogued assets in one asset class (integer meta; not a money value)."""

    asset_class: str
    count: int


class CatalogueBreakdown(CamelModel):
    """Read-only per-asset-class breakdown of the asset catalogue (derived summary; not a SoT)."""

    breakdown: list[AssetClassCount]
    total: int
    source: str


def catalogue_breakdown(market_data: MarketDataPort) -> CatalogueBreakdown:
    """Group the asset catalogue by ``asset_class`` (deterministic; fail-closed)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    counts: dict[str, int] = {}
    for asset in asset_catalog(market_data).assets:
        counts[asset.asset_class] = counts.get(asset.asset_class, 0) + 1
    ordered = [c for c in _CLASS_ORDER if c in counts] + sorted(
        c for c in counts if c not in _CLASS_ORDER
    )
    return CatalogueBreakdown(
        breakdown=[AssetClassCount(asset_class=c, count=counts[c]) for c in ordered],
        total=sum(counts.values()),
        source=SANDBOX_MOCK,
    )



class MarketAssetCount(CamelModel):
    """Count of markets in which one asset appears as base or quote (integer meta)."""

    asset: str
    count: int


class MarketsBreakdown(CamelModel):
    """Read-only per-base / per-quote market breakdown (derived summary; not a SoT)."""

    by_base: list[MarketAssetCount]
    by_quote: list[MarketAssetCount]
    total: int
    source: str


def markets_breakdown() -> MarketsBreakdown:
    """Count base/quote assets over the markets bundle (deterministic; fail-closed)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    markets = list_instrument_asset_xref()
    base_counts: dict[str, int] = {}
    quote_counts: dict[str, int] = {}
    for m in markets:
        base_counts[m.base_asset.asset] = base_counts.get(m.base_asset.asset, 0) + 1
        quote_counts[m.quote_asset.asset] = quote_counts.get(m.quote_asset.asset, 0) + 1

    def _to_list(counts: dict[str, int]) -> list[MarketAssetCount]:
        return [MarketAssetCount(asset=a, count=counts[a]) for a in sorted(counts)]

    return MarketsBreakdown(
        by_base=_to_list(base_counts),
        by_quote=_to_list(quote_counts),
        total=len(markets),
        source=SANDBOX_MOCK,
    )



class InstrumentDimensionCount(CamelModel):
    """Count of instruments sharing one value of a categorical dimension (integer meta)."""

    key: str
    count: int


class InstrumentsBreakdown(CamelModel):
    """Read-only instrument breakdown by fee-schedule / tick-size (derived summary; not a SoT)."""

    by_fee_schedule: list[InstrumentDimensionCount]
    by_tick_size: list[InstrumentDimensionCount]
    total: int
    source: str


def instruments_breakdown() -> InstrumentsBreakdown:
    """Count instruments by fee_schedule_ref / tick_size over list_instruments (deterministic)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    instruments = list_instruments()
    fee_counts: dict[str, int] = {}
    tick_counts: dict[str, int] = {}
    for inst in instruments:
        fee_counts[inst.fee_schedule_ref] = fee_counts.get(inst.fee_schedule_ref, 0) + 1
        tick_counts[inst.tick_size] = tick_counts.get(inst.tick_size, 0) + 1

    def _to_list(counts: dict[str, int]) -> list[InstrumentDimensionCount]:
        return [InstrumentDimensionCount(key=k, count=counts[k]) for k in sorted(counts)]

    return InstrumentsBreakdown(
        by_fee_schedule=_to_list(fee_counts),
        by_tick_size=_to_list(tick_counts),
        total=len(instruments),
        source=SANDBOX_MOCK,
    )



class SymbolDimensionCount(CamelModel):
    """Count of symbols sharing one value of a categorical symbol dimension (integer meta)."""

    key: str
    count: int


class SymbolsBreakdown(CamelModel):
    """Read-only symbol breakdown by status / precision (derived summary; not a SoT)."""

    by_status: list[SymbolDimensionCount]
    by_price_precision: list[SymbolDimensionCount]
    by_qty_precision: list[SymbolDimensionCount]
    total: int
    source: str


def symbols_breakdown(market_data: MarketDataPort) -> SymbolsBreakdown:
    """Count symbols by status / precision over list_symbols (deterministic; precision=str)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    symbols = market_data.list_symbols()
    status_counts: dict[str, int] = {}
    price_prec_counts: dict[str, int] = {}
    qty_prec_counts: dict[str, int] = {}
    for sym in symbols:
        status_counts[sym.status] = status_counts.get(sym.status, 0) + 1
        pp = str(sym.price_precision)
        qp = str(sym.qty_precision)
        price_prec_counts[pp] = price_prec_counts.get(pp, 0) + 1
        qty_prec_counts[qp] = qty_prec_counts.get(qp, 0) + 1

    def _to_list(counts: dict[str, int]) -> list[SymbolDimensionCount]:
        return [SymbolDimensionCount(key=k, count=counts[k]) for k in sorted(counts)]

    return SymbolsBreakdown(
        by_status=_to_list(status_counts),
        by_price_precision=_to_list(price_prec_counts),
        by_qty_precision=_to_list(qty_prec_counts),
        total=len(symbols),
        source=SANDBOX_MOCK,
    )



class AccountDimensionCount(CamelModel):
    """Count of advisory accounts sharing one value of a categorical dimension (integer meta)."""

    key: str
    count: int


class AccountsBreakdown(CamelModel):
    """Read-only account breakdown by type / ledger-nature / status (derived; not a SoT)."""

    by_account_type: list[AccountDimensionCount]
    by_ledger_nature: list[AccountDimensionCount]
    by_account_status: list[AccountDimensionCount]
    total: int
    source: str


def accounts_breakdown() -> AccountsBreakdown:
    """Count advisory accounts by type/ledger-nature/status (deterministic; no balances)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    accounts = account_metadata().accounts
    type_counts: dict[str, int] = {}
    nature_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for acct in accounts:
        type_counts[acct.account_type] = type_counts.get(acct.account_type, 0) + 1
        nature_counts[acct.ledger_nature] = nature_counts.get(acct.ledger_nature, 0) + 1
        status_counts[acct.account_status] = status_counts.get(acct.account_status, 0) + 1

    def _to_list(counts: dict[str, int]) -> list[AccountDimensionCount]:
        return [AccountDimensionCount(key=k, count=counts[k]) for k in sorted(counts)]

    return AccountsBreakdown(
        by_account_type=_to_list(type_counts),
        by_ledger_nature=_to_list(nature_counts),
        by_account_status=_to_list(status_counts),
        total=len(accounts),
        source=SANDBOX_MOCK,
    )



class NetworkCount(CamelModel):
    """Count of catalogued assets that list one blockchain network (integer meta)."""

    network: str
    count: int


class NetworkBreakdown(CamelModel):
    """Read-only per-network asset breakdown (flatten of asset networks; derived, not a SoT).

    Flatten semantics: an asset listing N networks contributes to N buckets; an asset with an empty
    networks list contributes to none. Therefore total_memberships (= sum of by_network counts)
    need NOT equal total_assets (the catalogue size).
    """

    by_network: list[NetworkCount]
    total_assets: int
    total_memberships: int
    source: str


def network_breakdown(market_data: MarketDataPort) -> NetworkBreakdown:
    """Flatten asset networks into per-network counts (deterministic; empty -> no bucket)."""
    from banxe_trading_backend.risk.greeks import SANDBOX_MOCK  # lazy: avoid import cycle

    assets = asset_catalog(market_data).assets
    counts: dict[str, int] = {}
    for asset in assets:
        for net in asset.networks:
            counts[net] = counts.get(net, 0) + 1
    return NetworkBreakdown(
        by_network=[NetworkCount(network=n, count=counts[n]) for n in sorted(counts)],
        total_assets=len(assets),
        total_memberships=sum(counts.values()),
        source=SANDBOX_MOCK,
    )
