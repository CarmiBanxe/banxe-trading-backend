"""S6.3b FINAL — dYdX submission transport behind the env gate (no real network).

A fake transport replaces the real HTTP relay so tests never open a connection.
Verifies: gate-closed default (no network), gate-open success/failure mapping into
the §D3 error model, and that Builder Codes in the client payload are relayed
unchanged. Only obviously-fake placeholders are used (confined to tests).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest

from banxe_trading_backend.config import Settings
from banxe_trading_backend.models import ExchangeOrderRequest, OrderSide, OrderType
from banxe_trading_backend.ports import (
    DydxExchangeAdapter,
    ExchangeUnavailable,
    InsufficientBalance,
    ValidationError,
)

FAKE_NODE_URL = "https://example-dydx-node.invalid"
FAKE_BUILDER_ADDRESS = "TEST_BUILDER_ADDRESS"
FAKE_BUILDER_FEE_PPM = 123


class RecordingTransport:
    """Fake DydxSubmissionTransport — records calls, returns a canned response."""

    def __init__(
        self,
        *,
        response: Mapping[str, object] | None = None,
        error: Exception | None = None,
    ):
        self._response = response if response is not None else {"txhash": "ABC123", "code": 0}
        self._error = error
        self.calls: list[tuple[str, Mapping[str, object], float]] = []

    async def submit(
        self, node_url: str, signed_order: Mapping[str, object], *, timeout_s: float
    ) -> Mapping[str, object]:
        self.calls.append((node_url, signed_order, timeout_s))
        if self._error is not None:
            raise self._error
        return self._response


def _adapter(transport: RecordingTransport, **kw: object) -> DydxExchangeAdapter:
    return DydxExchangeAdapter(
        submit_enabled=True,
        node_url=FAKE_NODE_URL,
        submission_transport=transport,
        **kw,  # type: ignore[arg-type]
    )


def _order() -> ExchangeOrderRequest:
    return ExchangeOrderRequest(
        base_asset="BTC",
        quote_asset="USD",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        amount="0.5",
        client_order_id="coid-1",
        correlation_id="corr-1",
        limit_price="67000",
        owner_address="0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A",
    )


# --------------------------- gate closed (default) -------------------------- #


def test_submit_disabled_default_makes_no_transport_call() -> None:
    transport = RecordingTransport()
    # Default settings → gate closed; even with a transport present, nothing is sent.
    adapter = DydxExchangeAdapter.from_settings(Settings())
    object.__setattr__(adapter, "_submission_transport", transport)
    with pytest.raises(ExchangeUnavailable, match="disabled"):
        asyncio.run(adapter.submit_signed_order({"signed": "tx"}))
    assert transport.calls == []  # no network/transport touched


# --------------------------- gate open: success ----------------------------- #


def test_submit_enabled_success_returns_result() -> None:
    transport = RecordingTransport(response={"txhash": "DEADBEEF", "code": 0, "raw_log": ""})
    adapter = _adapter(transport)
    result = asyncio.run(adapter.submit_signed_order({"signed": "tx", "tx_bytes": "..."}))
    assert result.order_id == "DEADBEEF"
    assert result.raw is not None
    assert result.raw["submitted"] is True
    # Relayed to the configured node URL with the env timeout, payload unchanged.
    node_url, payload, timeout = transport.calls[0]
    assert node_url == FAKE_NODE_URL
    assert payload == {"signed": "tx", "tx_bytes": "..."}
    assert timeout == 10.0


# --------------------------- gate open: failure mapping --------------------- #


def test_node_insufficient_funds_maps_to_insufficient_balance() -> None:
    transport = RecordingTransport(response={"code": 5, "raw_log": "insufficient funds for fee"})
    with pytest.raises(InsufficientBalance):
        asyncio.run(_adapter(transport).submit_signed_order({"signed": "tx"}))


def test_node_invalid_sequence_maps_to_validation_error() -> None:
    transport = RecordingTransport(response={"code": 32, "raw_log": "invalid sequence"})
    with pytest.raises(ValidationError):
        asyncio.run(_adapter(transport).submit_signed_order({"signed": "tx"}))


def test_node_generic_failure_maps_to_exchange_unavailable() -> None:
    transport = RecordingTransport(response={"code": 1, "raw_log": "mempool full"})
    with pytest.raises(ExchangeUnavailable):
        asyncio.run(_adapter(transport).submit_signed_order({"signed": "tx"}))


def test_transport_connection_error_maps_to_exchange_unavailable() -> None:
    transport = RecordingTransport(error=ConnectionError("dns failure"))
    with pytest.raises(ExchangeUnavailable, match="submission failed"):
        asyncio.run(_adapter(transport).submit_signed_order({"signed": "tx"}))


# --------------------------- Builder Codes with submit ---------------------- #


def test_buildercodes_in_payload_are_relayed_unchanged() -> None:
    # With Builder Codes envs + submit on, the intent carries builderCodeParameters.
    settings = Settings(
        dydx_submit_enabled=True,
        dydx_node_url=FAKE_NODE_URL,
        dydx_builder_address=FAKE_BUILDER_ADDRESS,
        dydx_builder_fee_ppm=FAKE_BUILDER_FEE_PPM,
    )
    transport = RecordingTransport()
    adapter = DydxExchangeAdapter.from_settings(settings)
    object.__setattr__(adapter, "_submission_transport", transport)

    intent = adapter.build_place_intent(_order())
    assert intent["builderCodeParameters"] == {
        "builderAddress": FAKE_BUILDER_ADDRESS,
        "feePpm": FAKE_BUILDER_FEE_PPM,
    }
    # The client signs a payload built from the intent; the backend relays it
    # UNCHANGED (no silent mutation of the signed content, incl. Builder Codes).
    signed_payload = {"unsignedIntent": intent, "signature": "0xfake"}
    asyncio.run(adapter.submit_signed_order(signed_payload))
    _, relayed, _ = transport.calls[0]
    assert relayed == signed_payload
    builder = relayed["unsignedIntent"]["builderCodeParameters"]  # type: ignore[index]
    assert builder == {"builderAddress": FAKE_BUILDER_ADDRESS, "feePpm": FAKE_BUILDER_FEE_PPM}
