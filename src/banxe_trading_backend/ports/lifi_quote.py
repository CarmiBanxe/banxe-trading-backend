"""LI.FI-backed QuotePort (ADR-083; S6.5).

Calls the PUBLIC LI.FI quote API (``https://li.quest/v1/quote``) — **no API key
required** for public quotes. Activated only via env (``BANXE_QUOTE_PROVIDER=lifi``);
the default provider stays the in-memory mock.

Self-custodial / API-only: a quote is a read-only estimate. Any resulting swap tx
is signed by the client wallet — the backend never signs and holds no keys.

Integrator / fee params are OPERATOR-GATED: attached ONLY when an integrator id
is set AND a positive fee is configured. The optional LI.FI API key is a seam
only (unused this sprint). All amounts are Decimal strings (I-01, never float).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from banxe_trading_backend.models import QuoteRequest, QuoteResponse

from .exchange_port import ExchangeError, ExchangeUnavailable, ValidationError

if TYPE_CHECKING:
    from banxe_trading_backend.config import Settings

_BPS_DENOMINATOR = Decimal(10_000)


# --------------------------------------------------------------------------- #
# Transport (injectable) — real impl hits the PUBLIC LI.FI API (no key)        #
# --------------------------------------------------------------------------- #


@runtime_checkable
class LifiQuoteTransport(Protocol):
    """Fetches a LI.FI quote. Injectable so CI never hits the network."""

    async def fetch_quote(
        self, base_url: str, params: Mapping[str, str], *, timeout_s: float
    ) -> Mapping[str, object]: ...


class HttpxLifiTransport:
    """Default transport: GET ``{base_url}/quote`` (public; no credentials).

    httpx is imported lazily so construction (and CI) never touches the network.
    No API key is sent in this sprint.
    """

    async def fetch_quote(
        self, base_url: str, params: Mapping[str, str], *, timeout_s: float
    ) -> Mapping[str, object]:
        import httpx  # local import: only needed when the live transport runs

        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_s) as client:
            resp = await client.get("/quote", params=dict(params))
            resp.raise_for_status()
            data: Mapping[str, object] = resp.json()
            return data


# --------------------------------------------------------------------------- #
# Response mapping helpers (Decimal / I-01)                                    #
# --------------------------------------------------------------------------- #


def _get_map(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _amount_str(value: object) -> str:
    """Atomic amount → validated decimal string (I-01; must be a string)."""
    if not isinstance(value, str):
        raise ValidationError("LI.FI amount must be a decimal string (I-01), never a float")
    try:
        Decimal(value)
    except InvalidOperation as exc:
        raise ValidationError(f"invalid LI.FI amount: {value!r}") from exc
    return value


def _ratio_str(value: object) -> str:
    """Slippage ratio (str or JSON number) → canonical decimal string."""
    try:
        return str(Decimal(str(value)))
    except InvalidOperation as exc:
        raise ValidationError(f"invalid LI.FI slippage: {value!r}") from exc


def map_lifi_quote(request: QuoteRequest, response: Mapping[str, object]) -> QuoteResponse:
    """Map a LI.FI quote response → our normalized QuoteResponse."""
    estimate = _get_map(response.get("estimate"))
    action = _get_map(response.get("action"))
    steps = response.get("includedSteps")
    hops = len(steps) if isinstance(steps, list) and steps else 1
    tool = response.get("tool")
    provider = tool if isinstance(tool, str) and tool else "unknown"

    to_amount = estimate.get("toAmount")
    if to_amount is None:
        raise ValidationError("LI.FI response missing estimate.toAmount")
    to_amount_min = estimate.get("toAmountMin")
    slippage = action.get("slippage")

    return QuoteResponse(
        from_chain=request.from_chain,
        to_chain=request.to_chain,
        from_token=request.from_token,
        to_token=request.to_token,
        amount=request.amount,
        estimated_return=_amount_str(to_amount),
        estimated_return_min=_amount_str(to_amount_min) if to_amount_min is not None else None,
        slippage=_ratio_str(slippage) if slippage is not None else None,
        provider=provider,
        hops=hops,
        route={"tool": provider, "steps": hops},
    )


# --------------------------------------------------------------------------- #
# Adapter                                                                      #
# --------------------------------------------------------------------------- #


class LifiQuoteAdapter:
    """QuotePort backed by the public LI.FI quote API (env-gated, no key)."""

    def __init__(
        self,
        *,
        base_url: str,
        integrator: str = "",
        fee_bps: int = 0,
        transport: LifiQuoteTransport | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = base_url
        self._integrator = integrator
        self._fee_bps = fee_bps
        self._transport: LifiQuoteTransport = (
            transport if transport is not None else HttpxLifiTransport()
        )
        self._timeout_s = timeout_s

    @classmethod
    def from_settings(cls, settings: Settings) -> LifiQuoteAdapter:
        return cls(
            base_url=settings.lifi_base_url,
            integrator=settings.lifi_integrator,
            fee_bps=settings.lifi_fee_bps,
            timeout_s=settings.lifi_timeout_s,
        )

    def _fee_enabled(self) -> bool:
        # OPERATOR-GATED: integrator + fee attached ONLY when BOTH are set.
        return bool(self._integrator) and self._fee_bps > 0

    def build_params(self, request: QuoteRequest) -> dict[str, str]:
        params: dict[str, str] = {
            "fromChain": request.from_chain,
            "toChain": request.to_chain,
            "fromToken": request.from_token,
            "toToken": request.to_token,
            "fromAmount": request.amount,
        }
        if request.from_address:
            params["fromAddress"] = request.from_address
        if request.slippage is not None:
            params["slippage"] = request.slippage
        if self._fee_enabled():
            params["integrator"] = self._integrator
            params["fee"] = str(Decimal(self._fee_bps) / _BPS_DENOMINATOR)
        return params

    async def get_quote(self, request: QuoteRequest) -> QuoteResponse:
        params = self.build_params(request)
        try:
            response = await self._transport.fetch_quote(
                self._base_url, params, timeout_s=self._timeout_s
            )
        except ExchangeError:
            raise
        except Exception as exc:  # noqa: BLE001 - any transport/connection error → §D3
            raise ExchangeUnavailable(f"LI.FI quote failed: {type(exc).__name__}") from exc
        return map_lifi_quote(request, response)
