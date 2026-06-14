"""DSE → unsigned execution-intent bridge (T9.1) + multi-venue preview (S16).

T9.1 maps a DSE *advisory action* (BUY / SELL / OPEN_LONG / OPEN_SHORT / CLOSE)
onto an UNSIGNED ``ExchangeOrderRequest`` via the configured ``ExchangePort``.
S16 ADDITIVELY hardens the same endpoint to a multi-venue / multi-product preview:
given ``venues`` / ``productType`` it returns a normalized ``candidates`` set with a
deterministic ``bestCandidate`` — still STRICTLY advisory.

STRICT SAFETY (ADR-083 self-custodial; sandbox/pre-production):
  * NOTHING is signed and NOTHING is submitted — ``signed``/``submitted`` are
    always false (per top-level and per candidate); the backend holds NO keys;
  * mock/sandbox by default — no live chain, no network, no real quotes/orderbooks;
  * deterministic for the same request; the legacy single-venue shape is unchanged;
  * any non-mock execution-preview provider, or submit/sign/live flags, fail closed.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from enum import Enum

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

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


class IntentType(str, Enum):
    SWAP = "swap"
    TRADE = "trade"
    STAKE = "stake"
    HEDGE = "hedge"


class PreviewProductType(str, Enum):
    SPOT = "spot"
    PERP = "perp"
    EARN = "earn"


class IntentPreviewRequest(CamelModel):
    # extra="forbid" → fail-closed on submit/sign/live or any unknown flag.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    asset: str
    notional_usd: DecimalStr
    # Legacy single-venue (T9.1) — optional now so multi-venue requests can omit it.
    action_type: ActionType | None = None
    venue: str = "mock"
    side: OrderSide | None = None  # optional override (e.g. for CLOSE)
    # S16 multi-venue (additive, optional).
    intent_type: IntentType | None = None
    quote_asset: str | None = None
    venues: list[str] | None = None
    product_type: PreviewProductType | None = None
    execution_mode: str = "preview-only"
    risk_profile: str | None = None


class MappedOrder(CamelModel):
    base_asset: str
    quote_asset: str
    side: OrderSide
    type: OrderType
    amount: DecimalStr
    reduce_only: bool


class ExecutionCandidate(CamelModel):
    venue: str
    route: str
    product_type: str
    expected_price: DecimalStr
    estimated_fee_usd: DecimalStr
    estimated_slippage_bps: DecimalStr
    eta_seconds: int
    confidence: DecimalStr
    signed: bool
    submitted: bool
    notes: list[str] | None = None


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
    # S16 additive multi-venue fields (null in legacy single-venue mode).
    intent_type: str | None = None
    product_type: str | None = None
    quote_asset: str | None = None
    candidates: list[ExecutionCandidate] | None = None
    best_candidate: ExecutionCandidate | None = None


# --- multi-venue mock parameters (fixtures only; deterministic) -------------- #

_VENUE_PARAMS: dict[str, dict[str, object]] = {
    "lifi": {"fee_bps": "8", "slip_bps": "18", "eta": 45},
    "0x": {"fee_bps": "12", "slip_bps": "22", "eta": 38},
    "dydx-v4": {"fee_bps": "5", "slip_bps": "10", "eta": 12},
    "gmx-v2": {"fee_bps": "10", "slip_bps": "15", "eta": 20},
    "injective": {"fee_bps": "7", "slip_bps": "14", "eta": 15},
    "stakekit": {"fee_bps": "0", "slip_bps": "0", "eta": 60},
    "aave-v3": {"fee_bps": "0", "slip_bps": "2", "eta": 30},
    "lido": {"fee_bps": "0", "slip_bps": "3", "eta": 40},
}
_DEFAULT_PARAMS = {"fee_bps": "15", "slip_bps": "30", "eta": 60}
_DEFAULT_VENUES: dict[str, list[str]] = {
    "spot": ["lifi", "0x"],
    "perp": ["dydx-v4", "gmx-v2", "injective"],
    "earn": ["stakekit", "aave-v3", "lido"],
}
_REF_PRICE: dict[str, str] = {
    "ETH": "3500", "BTC": "67250", "SOL": "150", "USDC": "1", "USDT": "1", "DAI": "1",
}


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


def build_execution_preview_provider(name: str) -> str:
    """Resolve the execution-preview provider. Only 'mock' is wired (default)."""
    if name == "mock":
        return "mock"
    # A live execution / submission / signing provider is OPERATOR-GATED (ODR).
    raise ValueError(
        f"execution preview provider {name!r} is not wired (operator-gated); only 'mock'"
    )


def _clamp(value: Decimal, lo: str, hi: str) -> Decimal:
    return max(Decimal(lo), min(Decimal(hi), value)).quantize(Decimal("0.01"))


def _candidate(venue: str, product: str, notional: Decimal, ref: Decimal) -> ExecutionCandidate:
    known = venue in _VENUE_PARAMS
    params = _VENUE_PARAMS.get(venue, _DEFAULT_PARAMS)
    fee_bps = Decimal(str(params["fee_bps"]))
    slip_bps = Decimal(str(params["slip_bps"]))
    eta = int(params["eta"])  # type: ignore[call-overload]
    fee_usd = (notional * fee_bps / Decimal(10000)).quantize(Decimal("0.01"))
    if product == "earn":
        price = ref.quantize(Decimal("0.01"))  # informational for earn
    else:
        price = (ref * (Decimal(1) - slip_bps / Decimal(10000))).quantize(Decimal("0.01"))
    confidence = _clamp(Decimal(1) - (fee_bps + slip_bps) / Decimal(200), "0.50", "0.95")
    notes = None if known else ["unknown venue — mock defaults"]
    return ExecutionCandidate(
        venue=venue,
        route=f"mock-{venue}-route",
        product_type=product,
        expected_price=str(price),
        estimated_fee_usd=str(fee_usd),
        estimated_slippage_bps=str(slip_bps.quantize(Decimal("0.01"))),
        eta_seconds=eta,
        confidence=str(confidence),
        signed=False,
        submitted=False,
        notes=notes,
    )


def _score(
    candidate: ExecutionCandidate, notional: Decimal, product: str, risk: str | None
) -> Decimal:
    slip_usd = notional * Decimal(candidate.estimated_slippage_bps) / Decimal(10000)
    score = -(Decimal(candidate.estimated_fee_usd) + slip_usd)
    score -= Decimal(candidate.eta_seconds) * Decimal("0.05")
    if candidate.venue in _DEFAULT_VENUES.get(product, []):
        score += Decimal("0.5")  # venue suitable for the product
    if risk == "conservative":
        score -= slip_usd * Decimal("0.5")  # extra slippage aversion
    elif risk == "aggressive":
        score -= Decimal(candidate.eta_seconds) * Decimal("0.1")  # prefers low ETA
    return score


class IntentPreviewService:
    """Unsigned intent preview — legacy single-venue (T9.1) + multi-venue (S16)."""

    def __init__(self, exchange: ExchangePort) -> None:
        self._exchange = exchange

    async def preview(self, request: IntentPreviewRequest) -> IntentPreviewResponse:
        if request.execution_mode != "preview-only":
            raise ValueError("executionMode must be 'preview-only' (live is operator-gated)")
        if not request.asset.strip():
            raise ValueError("asset must be non-empty")
        notional = Decimal(request.notional_usd)
        if notional <= 0:
            raise ValueError("notionalUsd must be > 0")

        multi = (
            request.venues is not None
            or request.product_type is not None
            or request.intent_type is not None
        )
        if multi:
            return self._multi_venue(request, notional)
        return await self._single_venue(request, notional)

    # --------------------------- S16 multi-venue ---------------------------- #

    def _multi_venue(
        self, request: IntentPreviewRequest, notional: Decimal
    ) -> IntentPreviewResponse:
        product = (request.product_type or PreviewProductType.SPOT).value
        intent_type = (request.intent_type or IntentType.SWAP).value
        if request.venues is not None:
            if not request.venues or any(not v.strip() for v in request.venues):
                raise ValueError("venues entries must be non-empty")
            venues = request.venues
        else:
            venues = _DEFAULT_VENUES[product]
        ref = Decimal(_REF_PRICE.get(request.asset.upper(), "100"))
        candidates = [_candidate(v, product, notional, ref) for v in venues]
        best = max(candidates, key=lambda c: _score(c, notional, product, request.risk_profile))
        return IntentPreviewResponse(
            tradable=True,
            mode="sandbox-mock",
            signed=False,
            submitted=False,
            reason=f"{len(candidates)} candidate(s) across venues; best: {best.venue}",
            venue=best.venue,
            disclaimer=_DISCLAIMER,
            intent_type=intent_type,
            product_type=product,
            quote_asset=request.quote_asset,
            candidates=candidates,
            best_candidate=best,
        )

    # --------------------------- T9.1 single-venue -------------------------- #

    async def _single_venue(
        self, request: IntentPreviewRequest, notional: Decimal
    ) -> IntentPreviewResponse:
        if request.action_type is None:
            raise ValueError("actionType is required for a single-venue preview")
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
        side = request.side or mapping[0]
        reduce_only = mapping[1]
        base, quote = _split_asset(request.asset)

        rate = await self._exchange.get_rate(base, quote)
        ask = Decimal(rate.ask)
        amount = (notional / ask).quantize(Decimal("0.00000001")) if ask > 0 else Decimal(0)

        client_order_id = _deterministic_id("intent", request.asset, side.value, str(notional))
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
