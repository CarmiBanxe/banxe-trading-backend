"""Advisory instrument trading-parameters (M1.9, config-as-data, read-only).

Single advisory source for per-symbol trading parameters (tick size, min/max order quantity,
fee-schedule reference), feeding the EXISTING frozen ``InstrumentInfo`` / ``GET
/instruments/{symbol}``. Replaces the prior hardcoded stub with a deterministic config-as-data
table keyed on the symbol universe (``SymbolInfo``/``MarketDataPort``).

It does NOT compute fees -- ``FeeEnginePort`` remains the fee-computation source-of-truth; only a
``fee_schedule_ref`` string is carried. It carries NO balances, amounts, positions, or order
state. READ-ONLY / advisory / mock-safe; fail-closed -- an unknown symbol raises
``InstrumentParamsError`` (never a fabricated value).
"""
from __future__ import annotations

from banxe_trading_backend.models import InstrumentInfo


class InstrumentParamsError(KeyError):
    """Unknown symbol -- no advisory trading parameters configured (fail-closed)."""


# config-as-data: per-symbol advisory trading parameters. tick/min/max are DecimalStr trading
# parameters (granularity & order-size limits), NOT balances/amounts. Keys align with the
# SymbolInfo universe (reused, not a second symbol list). fee_schedule_ref is a string reference.
_INSTRUMENT_PARAMS: dict[str, dict[str, str]] = {
    "BTC-EUR": {
        "tick_size": "0.01", "min_qty": "0.0001", "max_qty": "1000",
        "fee_schedule_ref": "spot-default",
    },
    "ETH-EUR": {
        "tick_size": "0.01", "min_qty": "0.0010", "max_qty": "5000",
        "fee_schedule_ref": "spot-default",
    },
}


def _normalize(symbol: str) -> str:
    return (symbol or "").replace("/", "-").upper()


def instrument_info(symbol: str) -> InstrumentInfo:
    """Advisory ``InstrumentInfo`` for a known symbol; fail-closed on unknown (no fake value)."""
    key = _normalize(symbol)
    cfg = _INSTRUMENT_PARAMS.get(key)
    if cfg is None:
        raise InstrumentParamsError(symbol)
    return InstrumentInfo(
        symbol=key,
        tick_size=cfg["tick_size"],
        min_qty=cfg["min_qty"],
        max_qty=cfg["max_qty"],
        fee_schedule_ref=cfg["fee_schedule_ref"],
    )



def list_instruments() -> list[InstrumentInfo]:
    """Deterministic advisory list of all configured instruments (single source; fail-closed).

    Reuses _INSTRUMENT_PARAMS + instrument_info -- no new DTO, no second catalogue. Entries
    are returned in sorted symbol order; a malformed config entry is skipped (never fabricated).
    """
    out: list[InstrumentInfo] = []
    for symbol in sorted(_INSTRUMENT_PARAMS):
        try:
            out.append(instrument_info(symbol))
        except Exception:
            continue  # fail-closed: skip malformed config entry (no fabricated instrument)
    return out
