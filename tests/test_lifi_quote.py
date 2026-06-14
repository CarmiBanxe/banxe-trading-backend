"""LI.FI QuotePort — mock default, env-gated LI.FI, fee/integrator gating, mapping.

No network: a RecordingTransport replaces the real HTTP client. Fake placeholders
(``https://example-lifi.invalid``, ``TEST_LIFI_INTEGRATOR``) are confined here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.models import QuoteRequest
from banxe_trading_backend.ports import (
    ExchangeUnavailable,
    LifiQuoteAdapter,
    MockQuoteAdapter,
    QuotePort,
    map_lifi_quote,
)

FAKE_LIFI_URL = "https://example-lifi.invalid"
FAKE_INTEGRATOR = "TEST_LIFI_INTEGRATOR"

# Representative LI.FI /quote response shape (fields we map).
LIFI_SAMPLE: dict[str, object] = {
    "type": "lifi",
    "tool": "1inch",
    "action": {"fromChainId": 1, "toChainId": 137, "slippage": 0.005},
    "estimate": {"fromAmount": "1000000", "toAmount": "994000", "toAmountMin": "989000"},
    "includedSteps": [{"tool": "1inch"}, {"tool": "across"}],
}


class RecordingTransport:
    """Fake LifiQuoteTransport — records params, returns a canned response."""

    def __init__(
        self,
        *,
        response: Mapping[str, object] | None = None,
        error: Exception | None = None,
    ):
        self._response = response if response is not None else LIFI_SAMPLE
        self._error = error
        self.calls: list[tuple[str, Mapping[str, str], float]] = []

    async def fetch_quote(
        self, base_url: str, params: Mapping[str, str], *, timeout_s: float
    ) -> Mapping[str, object]:
        self.calls.append((base_url, params, timeout_s))
        if self._error is not None:
            raise self._error
        return self._response


def _request() -> QuoteRequest:
    return QuoteRequest(
        from_chain="1",
        to_chain="137",
        from_token="USDC",
        to_token="USDC",
        amount="1000000",
        slippage="0.005",
    )


def _lifi(transport: RecordingTransport, **kw: object) -> LifiQuoteAdapter:
    return LifiQuoteAdapter(base_url=FAKE_LIFI_URL, transport=transport, **kw)  # type: ignore[arg-type]


# --------------------------- protocol / mock default ------------------------ #


def test_adapters_satisfy_quoteport_protocol() -> None:
    assert isinstance(MockQuoteAdapter(), QuotePort)
    assert isinstance(LifiQuoteAdapter(base_url=FAKE_LIFI_URL), QuotePort)


def test_mock_quote_is_deterministic_no_network() -> None:
    result = asyncio.run(MockQuoteAdapter().get_quote(_request()))
    assert result.provider == "mock"
    assert result.estimated_return == "990000"  # 1_000_000 * 0.99
    assert Decimal(result.estimated_return)  # I-01 decimal string


def test_app_default_quote_provider_is_mock() -> None:
    app = create_app(Settings())
    assert isinstance(app.state.quote, MockQuoteAdapter)


def test_app_lifi_provider_builds_adapter_without_network() -> None:
    app = create_app(Settings(quote_provider="lifi", lifi_base_url=FAKE_LIFI_URL))
    assert isinstance(app.state.quote, LifiQuoteAdapter)


def test_quote_endpoint_uses_mock_by_default() -> None:
    client = TestClient(create_app(Settings()))
    resp = client.get(
        "/api/v1/quote",
        params={
            "fromChain": "1",
            "toChain": "137",
            "fromToken": "USDC",
            "toToken": "USDC",
            "amount": "1000000",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "mock"
    assert body["estimatedReturn"] == "990000"


# --------------------------- lifi request building -------------------------- #


def test_lifi_builds_base_request_params() -> None:
    transport = RecordingTransport()
    adapter = _lifi(transport)
    asyncio.run(adapter.get_quote(_request()))
    _, params, timeout = transport.calls[0]
    assert params == {
        "fromChain": "1",
        "toChain": "137",
        "fromToken": "USDC",
        "toToken": "USDC",
        "fromAmount": "1000000",
        "slippage": "0.005",
    }
    assert "integrator" not in params and "fee" not in params  # gated off by default
    assert timeout == 10.0


# --------------------------- fee / integrator gating ------------------------ #


@pytest.mark.parametrize(
    ("integrator", "fee_bps", "attached"),
    [
        ("", 0, False),  # nothing set
        (FAKE_INTEGRATOR, 0, False),  # integrator set, fee not positive
        ("", 50, False),  # fee set, integrator missing
        (FAKE_INTEGRATOR, 50, True),  # BOTH set → attached
    ],
)
def test_integrator_fee_gating(integrator: str, fee_bps: int, attached: bool) -> None:
    transport = RecordingTransport()
    adapter = _lifi(transport, integrator=integrator, fee_bps=fee_bps)
    asyncio.run(adapter.get_quote(_request()))
    _, params, _ = transport.calls[0]
    assert ("integrator" in params) is attached
    assert ("fee" in params) is attached
    if attached:
        assert params["integrator"] == FAKE_INTEGRATOR
        assert params["fee"] == "0.005"  # 50 bps / 10_000


# --------------------------- response mapping (Decimal/I-01) ---------------- #


def test_map_lifi_response_to_decimal_models() -> None:
    result = map_lifi_quote(_request(), LIFI_SAMPLE)
    assert result.estimated_return == "994000"
    assert result.estimated_return_min == "989000"
    assert result.provider == "1inch"
    assert result.hops == 2
    assert result.slippage == "0.005"
    # All monetary fields are valid decimal strings (I-01, never float).
    assert Decimal(result.amount) and Decimal(result.estimated_return)
    assert Decimal(result.estimated_return_min or "0")


def test_lifi_transport_error_maps_to_exchange_unavailable() -> None:
    transport = RecordingTransport(error=ConnectionError("dns failure"))
    with pytest.raises(ExchangeUnavailable, match="LI.FI quote failed"):
        asyncio.run(_lifi(transport).get_quote(_request()))


def test_lifi_missing_to_amount_is_rejected() -> None:
    transport = RecordingTransport(response={"tool": "x", "estimate": {}, "action": {}})
    from banxe_trading_backend.ports import ValidationError

    with pytest.raises(ValidationError):
        asyncio.run(_lifi(transport).get_quote(_request()))
