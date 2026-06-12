"""Typed wire models (pydantic v2).

Money invariant (I-01): every price/quantity/amount is a **decimal string**,
never a float. ``DecimalStr`` validates that each value parses as ``Decimal``
and rejects non-string input, so a float can never enter a money field.

Field names mirror ADR-021 §D2/§D3 and the frontend shapes from HANDOFF IL-188.
API/response models are camelCase on the wire (FE-facing); the order-book WS
envelope uses the verbatim FE keys (all single words, unaffected by aliasing).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


def _decimal_str(value: str) -> str:
    """Validate a money value is a parseable decimal string (I-01: no float)."""
    if not isinstance(value, str):  # pragma: no cover - pydantic rejects non-str first
        raise TypeError("money must be a decimal string (I-01), never a float")
    try:
        Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal string: {value!r}") from exc
    return value


DecimalStr = Annotated[str, AfterValidator(_decimal_str)]


class CamelModel(BaseModel):
    """Base model: camelCase aliases on the wire, snake_case in Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --- enums (ADR-021 / exchangeport-CONTRACT-SPEC) ---


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderState(str, Enum):
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# --- order book (WS) — verbatim FE shapes (single-word keys) ---


class RawPriceLevel(CamelModel):
    price: DecimalStr
    quantity: DecimalStr


class RawOrderBookSnapshot(CamelModel):
    bids: list[RawPriceLevel]
    asks: list[RawPriceLevel]
    sequence: int


class RawOrderBookDiff(CamelModel):
    bids: list[RawPriceLevel]
    asks: list[RawPriceLevel]
    sequence: int


class WsSnapshotMessage(CamelModel):
    type: Literal["snapshot"] = "snapshot"
    data: RawOrderBookSnapshot


class WsDiffMessage(CamelModel):
    type: Literal["diff"] = "diff"
    data: RawOrderBookDiff


# --- orders / rate (REST) ---


class PlaceOrderRequest(CamelModel):
    """FE REST body: symbol + camelCase order fields (ADR-021 §D3)."""

    symbol: str
    side: OrderSide
    type: OrderType
    amount: DecimalStr
    client_order_id: str
    correlation_id: str
    limit_price: DecimalStr | None = None


class ExchangeOrderRequest(CamelModel):
    """ExchangePort-shaped order (base/quote split) — payment-core contract."""

    base_asset: str
    quote_asset: str
    side: OrderSide
    type: OrderType
    amount: DecimalStr
    client_order_id: str
    correlation_id: str
    limit_price: DecimalStr | None = None


class OrderResult(CamelModel):
    order_id: str
    state: OrderState
    filled_amount: DecimalStr
    average_price: DecimalStr | None = None
    fee: DecimalStr | None = None
    raw: dict[str, object] | None = None


class CancelResult(CamelModel):
    order_id: str
    cancelled: bool


class RateQuote(CamelModel):
    base_asset: str
    quote_asset: str
    bid: DecimalStr
    ask: DecimalStr
    ttl_seconds: int
    quoted_at: str  # ISO 8601 UTC


# --- symbols / instruments (REST) ---


class SymbolInfo(CamelModel):
    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int
    qty_precision: int
    status: str


class InstrumentInfo(CamelModel):
    symbol: str
    tick_size: DecimalStr
    min_qty: DecimalStr
    max_qty: DecimalStr
    fee_schedule_ref: str


def split_symbol(symbol: str) -> tuple[str, str]:
    """Split ``BASE-QUOTE`` (or ``BASE/QUOTE``) into ``(base, quote)``."""
    sep = "-" if "-" in symbol else "/"
    base, _, quote = symbol.partition(sep)
    if not base or not quote:
        raise ValueError(f"invalid symbol {symbol!r}; expected BASE-QUOTE")
    return base.upper(), quote.upper()


# --- wallet auth (SIWE / EIP-4361; ADR-083 D4) ---


class NonceResponse(CamelModel):
    nonce: str
    issued_at: str  # ISO 8601 UTC
    expires_at: str


class VerifyRequest(CamelModel):
    """A signed SIWE (EIP-4361) message + its signature."""

    message: str
    signature: str


class SessionResponse(CamelModel):
    address: str
    token: str  # opaque, HMAC-signed; the backend holds no private keys
    expires_at: str
