"""dYdX v4 ExchangePort adapter — UNSIGNED intent construction (ADR-083, S6.3a).

**Self-custodial:** this backend NEVER signs or holds keys. It CONSTRUCTS an
**unsigned dYdX order intent** (the order parameters the user's wallet must sign)
and returns it; the SIWE-authenticated client (S6.4) signs and submits. The
backend does **NOT** submit signed transactions in this step — live submission
is OPERATOR-GATED (real node endpoint + the user's wallet), deferred to S6.3b.

**API-ONLY (AGPL):** no dYdX/AGPL code is vendored. We reproduce the *public*
quantum/subtick conversion (documented in `dydxprotocol/v4-clients`
`v4-client-py-v2/.../node/market.py`) in **Decimal** (I-01 — never float, which
is stronger than the upstream float implementation). Market params come from the
public Indexer metadata (here: representative defaults for the MVP markets).

**Builder Codes:** an optional revenue-share field set (builder_address +
fee_ppm). OPERATOR-GATED — empty / no-op by default; attached only when both env
values are configured. No real address/fee is committed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from urllib.parse import urlparse

from banxe_trading_backend.models import (
    ExchangeOrderRequest,
    OrderResult,
    OrderState,
    OrderType,
    RateQuote,
    TimeInForce,
)

from .exchange_port import (
    ComplianceBlock,
    ExchangeError,
    ExchangeUnavailable,
    InsufficientBalance,
    ValidationError,
)

if TYPE_CHECKING:
    from banxe_trading_backend.config import Settings

# dYdX fixes the quote atomic resolution at -6 (USDC has 6 decimals).
_QUOTE_QUANTUMS_ATOMIC_RESOLUTION = -6


@dataclass(frozen=True)
class DydxMarketParams:
    """Per-market quantization params (from the public Indexer metadata)."""

    ticker: str
    atomic_resolution: int
    quantum_conversion_exponent: int
    step_base_quantums: int
    subticks_per_tick: int


@dataclass(frozen=True)
class BuilderCodes:
    """Builder Codes revenue-share (OPERATOR-GATED)."""

    builder_address: str
    fee_ppm: int


# Representative MVP market params (mainnet-shaped). The live adapter refreshes
# these from the public Indexer `perpetualMarkets` (API-only) in S6.3b.
_DEFAULT_MARKETS: dict[str, DydxMarketParams] = {
    "BTC-USD": DydxMarketParams("BTC-USD", -10, -9, 1_000_000, 100_000),
    "ETH-USD": DydxMarketParams("ETH-USD", -9, -9, 1_000_000, 100_000),
}


def _round_down(value: Decimal, multiple: int) -> int:
    """floor(value / multiple) * multiple — pure integer/Decimal, no float."""
    units = int(value // multiple)
    return units * multiple


def calculate_quantums(size: Decimal, market: DydxMarketParams) -> int:
    """size (human) → base quantums (atomic units). Decimal, I-01, never float."""
    raw = size * (Decimal(10) ** (-market.atomic_resolution))
    quantums = _round_down(raw, market.step_base_quantums)
    return max(quantums, market.step_base_quantums)


def calculate_subticks(price: Decimal, market: DydxMarketParams) -> int:
    """price (human) → subticks (atomic). Decimal, I-01, never float."""
    exponent = (
        market.atomic_resolution
        - market.quantum_conversion_exponent
        - _QUOTE_QUANTUMS_ATOMIC_RESOLUTION
    )
    raw = price * (Decimal(10) ** exponent)
    subticks = _round_down(raw, market.subticks_per_tick)
    return max(subticks, market.subticks_per_tick)


def _client_id(client_order_id: str) -> int:
    """Deterministic uint32 dYdX client id derived from the client_order_id."""
    return int.from_bytes(hashlib.sha256(client_order_id.encode()).digest()[:4], "big")


_NODE_URL_SCHEMES = frozenset({"http", "https", "grpc", "grpcs", "tcp"})


def is_valid_node_url(url: str | None) -> bool:
    """True only for a non-empty URL with a recognised scheme + host.

    No real endpoint is encoded here; this is pure syntactic validation so the
    submission gate flips deterministically once an operator supplies a URL.
    Public so the S6.4-EN exchange-route resolver shares the same syntactic test.
    """
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in _NODE_URL_SCHEMES and bool(parsed.netloc)


def _builder_codes_from_settings(settings: Settings) -> BuilderCodes | None:
    """Builder Codes attach ONLY when BOTH an address and a positive fee are set.

    Default (address unset OR fee <= 0) → None → no builder fields on intents.
    """
    if settings.dydx_builder_address and settings.dydx_builder_fee_ppm > 0:
        return BuilderCodes(
            builder_address=settings.dydx_builder_address,
            fee_ppm=settings.dydx_builder_fee_ppm,
        )
    return None


def _extract_code(response: Mapping[str, object]) -> int | None:
    """Cosmos broadcast carries a top-level ``code``; CometBFT JSON-RPC nests it."""
    code = response.get("code")
    if code is None:
        result = response.get("result")
        if isinstance(result, Mapping):
            code = result.get("code")
    return int(code) if isinstance(code, int) else None


def _extract_txhash(response: Mapping[str, object]) -> str | None:
    for key in ("txhash", "txHash", "hash"):
        value = response.get(key)
        if isinstance(value, str) and value:
            return value
    result = response.get("result")
    if isinstance(result, Mapping):
        value = result.get("hash")
        if isinstance(value, str) and value:
            return value
    return None


def _node_raw_log(response: Mapping[str, object]) -> str:
    for key in ("raw_log", "rawLog", "log"):
        value = response.get(key)
        if isinstance(value, str):
            return value
    return ""


def _map_node_failure(code: int | None, raw_log: str) -> ExchangeError:
    """Map a dYdX node rejection into the §D3 error hierarchy."""
    log = raw_log.lower()
    if "insufficient" in log:
        return InsufficientBalance(f"dYdX node rejected order: {raw_log}")
    if "sanction" in log or "blocked" in log or "compliance" in log:
        return ComplianceBlock(f"dYdX node blocked order: {raw_log}")
    if "invalid" in log or "sequence" in log or "signature" in log:
        return ValidationError(f"dYdX node rejected order: {raw_log}")
    return ExchangeUnavailable(f"dYdX node rejected order (code {code}): {raw_log}")


def _result_from_node_response(response: Mapping[str, object]) -> OrderResult:
    """Map a node broadcast response → OrderResult (success) or §D3 error."""
    code = _extract_code(response)
    txhash = _extract_txhash(response)
    if code in (0, None) and txhash is not None:
        # Accepted by the node (tx broadcast). Fills are read via the Indexer later.
        return OrderResult(
            order_id=txhash,
            state=OrderState.ACCEPTED,
            filled_amount="0",
            raw={"submitted": True, "node": dict(response)},
        )
    raise _map_node_failure(code, _node_raw_log(response))


@runtime_checkable
class DydxSubmissionTransport(Protocol):
    """Relays an ALREADY-signed order to a dYdX node. Injectable so CI mocks it.

    Pure relay: the backend never signs and holds no keys. The endpoint URL is
    operator-supplied via env (no hard-coded host). Returns the node's response;
    raises on transport/connection failure (mapped to §D3 by the adapter).
    """

    async def submit(
        self, node_url: str, signed_order: Mapping[str, object], *, timeout_s: float
    ) -> Mapping[str, object]: ...


class HttpxSubmissionTransport:
    """Default transport: POST the client-signed payload to the node URL (HTTPS).

    No credentials (public submission of a signed tx). No hard-coded endpoint —
    the full submission URL is the operator's ``BANXE_DYDX_NODE_URL``. httpx is
    imported lazily so construction (and CI) never touches the network.
    """

    async def submit(
        self, node_url: str, signed_order: Mapping[str, object], *, timeout_s: float
    ) -> Mapping[str, object]:
        import httpx  # local import: only needed when live submission actually runs

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(node_url, json=dict(signed_order))
            resp.raise_for_status()
            data: Mapping[str, object] = resp.json()
            return data


class DydxExchangeAdapter:
    """ExchangePort that builds UNSIGNED dYdX intents, and (gated) relays signed ones.

    Self-custodial / API-only: the backend NEVER signs and holds NO keys. When the
    operator opens the submission gate (env), ``submit_signed_order`` relays a
    client-signed payload to the node and maps the response to the §D3 model.
    """

    def __init__(
        self,
        *,
        markets: Mapping[str, DydxMarketParams] | None = None,
        builder_codes: BuilderCodes | None = None,
        subaccount_number: int = 0,
        submit_enabled: bool = False,
        node_url: str | None = None,
        submission_transport: DydxSubmissionTransport | None = None,
        submit_timeout_s: float = 10.0,
    ) -> None:
        self._markets = dict(markets) if markets is not None else dict(_DEFAULT_MARKETS)
        self._builder_codes = builder_codes
        self._subaccount_number = subaccount_number
        # Live-submission gate inputs (S6.3b). Both must be satisfied; default off.
        self._submit_enabled = submit_enabled
        self._node_url = node_url
        self._submission_transport: DydxSubmissionTransport = (
            submission_transport if submission_transport is not None else HttpxSubmissionTransport()
        )
        self._submit_timeout_s = submit_timeout_s

    @classmethod
    def from_settings(cls, settings: Settings) -> DydxExchangeAdapter:
        return cls(
            builder_codes=_builder_codes_from_settings(settings),
            subaccount_number=settings.dydx_subaccount_number,
            submit_enabled=settings.dydx_submit_enabled,
            node_url=settings.dydx_node_url,
            submit_timeout_s=settings.dydx_submit_timeout_s,
        )

    # --- live-submission gate (S6.3b) -------------------------------------- #

    def submission_enabled(self) -> bool:
        """Live submission requires BOTH the env flag AND a valid node URL.

        Default (flag off OR node URL missing/invalid) → False, so behaviour is
        identical to S6.3a: unsigned intents only, ``submitted: false``, and NO
        network call is ever made.
        """
        return self._submit_enabled and is_valid_node_url(self._node_url)

    async def submit_signed_order(self, signed_order: Mapping[str, object]) -> OrderResult:
        """Relay a CLIENT-signed order to the dYdX node (S6.3b-final).

        Self-custodial / API-only: the backend NEVER signs and holds NO keys — it
        only broadcasts a payload the wallet already signed, and reads the node's
        response. Gated by ``submission_enabled()``:

        * gate CLOSED (default — flag off OR node URL missing/invalid) → raise
          ``ExchangeUnavailable("live submission disabled …")``; NO network I/O.
        * gate OPEN → POST the *unmodified* signed payload to the operator's
          ``BANXE_DYDX_NODE_URL`` via the injected transport, then map the node
          response (success / failure) into the §D3 error model.

        Enabling submission is purely an operator env decision (OPERATOR DECISION
        REQUIRED). Builder Codes live inside the client-built payload and are NOT
        required for submission; this method never mutates the signed content.
        """
        if not self.submission_enabled():
            raise ExchangeUnavailable(
                "live submission disabled — set BANXE_DYDX_SUBMIT_ENABLED and a valid "
                "BANXE_DYDX_NODE_URL (operator-gated)"
            )
        # node_url is guaranteed valid here by submission_enabled().
        node_url = self._node_url
        assert node_url is not None  # noqa: S101 - invariant of submission_enabled()
        try:
            response = await self._submission_transport.submit(
                node_url, signed_order, timeout_s=self._submit_timeout_s
            )
        except ExchangeError:
            raise  # a transport may already speak the §D3 model — pass it through
        except Exception as exc:  # noqa: BLE001 - any transport/connection error → §D3
            raise ExchangeUnavailable(
                f"dYdX node submission failed: {type(exc).__name__}"
            ) from exc
        return _result_from_node_response(response)

    # --- intent construction (the testable core) --------------------------- #

    def build_place_intent(self, order: ExchangeOrderRequest) -> dict[str, object]:
        ticker = f"{order.base_asset.upper()}-{order.quote_asset.upper()}"
        market = self._markets.get(ticker)
        if market is None:
            raise ValidationError(f"unknown dYdX market: {ticker}")
        if not order.owner_address:
            raise ValidationError("owner address (wallet session) is required")

        size = Decimal(order.amount)
        if size <= 0:
            raise ValidationError("order size must be positive")
        quantums = calculate_quantums(size, market)

        subticks: int | None = None
        price = order.limit_price
        if order.type is OrderType.LIMIT:
            if price is None:
                raise ValidationError("limit order requires a price")
            subticks = calculate_subticks(Decimal(price), market)
        # MARKET: no price input → subticks (slippage bound) supplied client-side.

        tif = order.time_in_force or (
            TimeInForce.GTT if order.type is OrderType.LIMIT else TimeInForce.IOC
        )

        return {
            "market": ticker,
            "ownerAddress": order.owner_address,
            "subaccountNumber": self._subaccount_number,
            "clientId": _client_id(order.client_order_id),
            "side": order.side.value.upper(),
            "orderType": order.type.value.upper(),
            "size": str(size),
            "price": price,  # human decimal string (limit) or None (market)
            "quantums": str(quantums),  # atomic integer string (I-01)
            "subticks": str(subticks) if subticks is not None else None,
            "timeInForce": tif.value,
            "reduceOnly": order.reduce_only,
            # chain params (good-til) require a node query — OPERATOR-GATED (S6.3b).
            "goodTilBlock": None,
            "goodTilBlockTime": None,
            "builderCodeParameters": self._builder_params(),
            "requiresClientSignature": True,
            "submitted": False,
        }

    def build_cancel_intent(self, order_id: str) -> dict[str, object]:
        return {
            "ordersToCancel": [order_id],
            "subaccountNumber": self._subaccount_number,
            "goodTilBlock": None,  # chain param — OPERATOR-GATED (S6.3b)
            "requiresClientSignature": True,
            "submitted": False,
        }

    def _builder_params(self) -> dict[str, object] | None:
        # Gated: attach ONLY when a non-empty address AND a positive fee are set.
        codes = self._builder_codes
        if codes is None or not codes.builder_address or codes.fee_ppm <= 0:
            return None  # no-op default
        return {
            "builderAddress": codes.builder_address,
            "feePpm": codes.fee_ppm,
        }

    # --- ExchangePort surface ---------------------------------------------- #

    async def place_order(self, order: ExchangeOrderRequest) -> OrderResult:
        intent = self.build_place_intent(order)
        # order_id is the client_order_id until a signed order lands on-chain (S6.3b).
        return OrderResult(
            order_id=order.client_order_id,
            state=OrderState.ACCEPTED,  # intent accepted for client signing
            filled_amount="0",
            raw={
                "unsignedIntent": intent,
                "requiresClientSignature": True,
                "submitted": False,
            },
        )

    async def cancel_order(self, order_id: str) -> bool:
        # Constructs the unsigned cancel intent (validates constructibility).
        # True = ready for client signing; the backend does not submit (S6.3b).
        self.build_cancel_intent(order_id)
        return True

    async def get_order_status(self, order_id: str) -> OrderResult:
        # Status requires the Indexer query (API-only) — OPERATOR-GATED to S6.3b.
        raise ExchangeUnavailable("dYdX order status requires the Indexer query (gated to S6.3b)")

    async def get_rate(self, base: str, quote: str) -> RateQuote:
        # Rate requires the Indexer markets query — OPERATOR-GATED to S6.3b.
        raise ExchangeUnavailable("dYdX rate requires the Indexer query (gated to S6.3b)")
