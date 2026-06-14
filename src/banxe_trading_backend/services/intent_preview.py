"""DSE → unsigned execution-intent bridge (T9.1) — internal, mock/sandbox-only.

Maps a DSE *advisory action* (BUY / SELL / OPEN_LONG / OPEN_SHORT / CLOSE) onto an
``ExchangeOrderRequest`` and returns the **UNSIGNED execution intent** built by the
configured ``ExchangePort`` (mock by default; dYdX builds unsigned intents too).
This is the canonical "advice → unsigned intent" link of the end-to-end trajectory.

STRICT SAFETY (ADR-083 self-custodial; sandbox/pre-production):
  * NOTHING is signed and NOTHING is submitted — the response is a PREVIEW only;
  * the backend holds NO keys; the client wallet signs client-side (out of scope);
  * mock/sandbox by default — no live chain, no real execution, no network;
  * advisory actions that are not directly tradable (STAKE / HEDGE / HOLD / WAIT /
    REBALANCE / ADJUST_SL / SWAP) return ``tradable: false`` with no intent.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from banxe_trading_backend.dse.models import ActionType
from banxe_trading_backend.models import (
    CamelModel,
    DecimalStr,
    ExchangeOrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
    split_symbol,
)
from banxe_trading_backend.ports import ExchangePort

# Common quote suffixes for DSE joined symbols (e.g. "BTCUSDT" → BTC / USDT).
_QUOTES = ("USDT", "USDC", "USD", "DAI", "EUR", "BTC", "ETH")

# Advisory action → (order side, reduce-only). Only these are directly tradable.
_TRADABLE: dict[ActionType, tuple[OrderSide, bool]] = {
    ActionType.BUY: (OrderSide.BUY, False),
    ActionType.OPEN_LONG: (OrderSide.BUY, False),
    ActionType.SELL: (OrderSide.SELL, False),
    ActionType.OPEN_SHORT: (OrderSide.SELL, False),
    ActionType.CLOSE: (OrderSide.SELL, True),  # close a long by default (override via side)
}

_DISCLAIMER = (
    "Sandbox/pre-production preview — UNSIGNED intent only. Nothing is signed, "
    "submitted, or executed; the backend holds no keys and the client wallet signs "
    "client-side. Mock data, no live chain. Advisory (ADR-083 self-custodial); NOT "
    "an order, NOT execution, NO SLA / billing."
)


class IntentPreviewRequest(CamelModel):
    asset: str
    action_type: ActionType
    notional_usd: DecimalStr
    venue: str = "mock"
    side: OrderSide | None = None  # optional override (e.g. for CLOSE)


class MappedOrder(CamelModel):
    base_asset: str
    quote_asset: str
    side: OrderSide
    type: OrderType
    amount: DecimalStr
    reduce_only: bool


class IntentPreviewResponse(CamelModel):
    tradable: bool
    mode: str
    signed: bool
    submitted: bool
    reason: str
    venue: str
    order: MappedOrder | None = None
    intent: OrderResult | None = None
    disclaimer: str


def _split_asset(asset: str) -> tuple[str, str]:
    if "-" in asset or "/" in asset:
        return split_symbol(asset)
    upper = asset.upper()
    for quote in sorted(_QUOTES, key=len, reverse=True):
        if upper.endswith(quote) and len(upper) > len(quote):
            return upper[: -len(quote)], quote
    raise ValueError(f"cannot split asset {asset!r} into base/quote")


def _deterministic_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


class IntentPreviewService:
    """Builds an unsigned intent preview from an advisory action (mock/sandbox)."""

    def __init__(self, exchange: ExchangePort) -> None:
        self._exchange = exchange

    async def preview(self, request: IntentPreviewRequest) -> IntentPreviewResponse:
        mapping = _TRADABLE.get(request.action_type)
        if mapping is None:
            return IntentPreviewResponse(
                tradable=False,
                mode="sandbox-mock",
                signed=False,
                submitted=False,
                reason=(
                    f"action {request.action_type.value} is advisory-only "
                    "(not directly tradable)"
                ),
                venue=request.venue,
                disclaimer=_DISCLAIMER,
            )
        notional = Decimal(request.notional_usd)
        if notional <= 0:
            raise ValueError("notionalUsd must be > 0")
        side = request.side or mapping[0]
        reduce_only = mapping[1]
        base, quote = _split_asset(request.asset)

        # Size the base amount from the notional via a mock rate (no network).
        rate = await self._exchange.get_rate(base, quote)
        ask = Decimal(rate.ask)
        amount = (notional / ask).quantize(Decimal("0.00000001")) if ask > 0 else Decimal(0)

        client_order_id = _deterministic_id(
            "intent", request.asset, side.value, str(notional)
        )
        order = ExchangeOrderRequest(
            base_asset=base,
            quote_asset=quote,
            side=side,
            type=OrderType.MARKET,
            amount=str(amount),
            client_order_id=client_order_id,
            correlation_id=_deterministic_id("corr", client_order_id),
            reduce_only=reduce_only,
            owner_address=None,  # self-custodial; the client signs, no key here
        )
        result = await self._exchange.place_order(order)
        # Safety-rail: a preview must NEVER come back submitted (defensive).
        if isinstance(result.raw, dict) and result.raw.get("submitted") is True:
            raise ValueError("execution preview must not submit — refusing")
        return IntentPreviewResponse(
            tradable=True,
            mode="sandbox-mock",
            signed=False,
            submitted=False,
            reason=f"unsigned {side.value} intent built for {base}/{quote}",
            venue=request.venue,
            order=MappedOrder(
                base_asset=base,
                quote_asset=quote,
                side=side,
                type=OrderType.MARKET,
                amount=str(amount),
                reduce_only=reduce_only,
            ),
            intent=result,
            disclaimer=_DISCLAIMER,
        )
