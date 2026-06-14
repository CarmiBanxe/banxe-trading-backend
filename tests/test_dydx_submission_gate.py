"""S6.3b PREP — live-submission & Builder Codes gating (no network/keys).

Verifies that toggling the env flags affects EXACTLY submission capability and
Builder Codes attachment, and nothing else. Default behaviour stays identical to
S6.3a: unsigned intents only, ``submitted: false``, no network, no builder fields.
Only obviously-fake placeholders are used (confined to this test).
"""

from __future__ import annotations

import asyncio

import pytest

from banxe_trading_backend.config import Settings
from banxe_trading_backend.models import ExchangeOrderRequest, OrderSide, OrderType
from banxe_trading_backend.ports import DydxExchangeAdapter, ExchangeUnavailable

# Obviously-fake placeholders — NOT real endpoints/addresses. Tests only.
FAKE_NODE_URL = "https://example-dydx-node.invalid"
FAKE_BUILDER_ADDRESS = "TEST_BUILDER_ADDRESS"
FAKE_BUILDER_FEE_PPM = 123


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


def _intent(settings: Settings) -> dict[str, object]:
    return DydxExchangeAdapter.from_settings(settings).build_place_intent(_order())


# --------------------------- submission gate -------------------------------- #


def test_submit_disabled_by_default() -> None:
    adapter = DydxExchangeAdapter.from_settings(Settings())
    assert adapter.submission_enabled() is False
    # No network, no submission: the seam refuses before any transport.
    with pytest.raises(ExchangeUnavailable, match="disabled"):
        asyncio.run(adapter.submit_signed_order({"signed": "tx"}))
    # place_order behaviour unchanged: unsigned intent, submitted:false.
    result = asyncio.run(adapter.place_order(_order()))
    assert result.raw is not None
    assert result.raw["submitted"] is False


@pytest.mark.parametrize(
    ("submit_enabled", "node_url", "expected"),
    [
        (False, None, False),  # both off
        (True, None, False),  # flag on, url missing
        (True, "", False),  # flag on, url empty
        (True, "not-a-url", False),  # flag on, url has no scheme/host
        (False, FAKE_NODE_URL, False),  # url set, flag off
        (True, FAKE_NODE_URL, True),  # BOTH satisfied
    ],
)
def test_submission_requires_both_flag_and_valid_url(
    submit_enabled: bool, node_url: str | None, expected: bool
) -> None:
    adapter = DydxExchangeAdapter.from_settings(
        Settings(dydx_submit_enabled=submit_enabled, dydx_node_url=node_url)
    )
    assert adapter.submission_enabled() is expected


def test_submit_enabled_routes_to_transport_no_real_network() -> None:
    # Gate open → the signed payload is relayed via the (injected fake) transport.
    # The fake records the call and returns success — NO real network is touched.
    seen: list[tuple[str, object]] = []

    class _FakeTransport:
        async def submit(self, node_url: str, signed_order: object, *, timeout_s: float) -> dict:
            seen.append((node_url, signed_order))
            return {"txhash": "FAKEHASH", "code": 0}

    adapter = DydxExchangeAdapter(
        submit_enabled=True,
        node_url=FAKE_NODE_URL,
        submission_transport=_FakeTransport(),
    )
    assert adapter.submission_enabled() is True
    result = asyncio.run(adapter.submit_signed_order({"signed": "tx"}))
    assert seen == [(FAKE_NODE_URL, {"signed": "tx"})]  # relayed unchanged
    assert result.raw is not None and result.raw["submitted"] is True


def test_enabling_submission_does_not_change_intent_output() -> None:
    off = _intent(Settings())
    on = _intent(Settings(dydx_submit_enabled=True, dydx_node_url=FAKE_NODE_URL))
    # Toggling submission flags affects submission capability ONLY — not the intent.
    assert off == on
    assert on["submitted"] is False
    assert on["builderCodeParameters"] is None


# --------------------------- Builder Codes gate ----------------------------- #


def test_buildercodes_absent_by_default() -> None:
    assert _intent(Settings())["builderCodeParameters"] is None


@pytest.mark.parametrize(
    ("address", "fee", "expected_present"),
    [
        (None, 0, False),  # nothing set
        (FAKE_BUILDER_ADDRESS, 0, False),  # address set, fee not positive
        (None, FAKE_BUILDER_FEE_PPM, False),  # fee set, address missing
        ("", FAKE_BUILDER_FEE_PPM, False),  # empty address
        (FAKE_BUILDER_ADDRESS, FAKE_BUILDER_FEE_PPM, True),  # BOTH satisfied
    ],
)
def test_buildercodes_require_both_address_and_positive_fee(
    address: str | None, fee: int, expected_present: bool
) -> None:
    settings = Settings(dydx_builder_address=address, dydx_builder_fee_ppm=fee)
    params = _intent(settings)["builderCodeParameters"]
    assert (params is not None) is expected_present


def test_buildercodes_enabled_attaches_fields() -> None:
    settings = Settings(
        dydx_builder_address=FAKE_BUILDER_ADDRESS,
        dydx_builder_fee_ppm=FAKE_BUILDER_FEE_PPM,
    )
    intent = _intent(settings)
    assert intent["builderCodeParameters"] == {
        "builderAddress": FAKE_BUILDER_ADDRESS,
        "feePpm": FAKE_BUILDER_FEE_PPM,
    }
    # Builder Codes change ONLY the builder field — submission stays off.
    assert intent["submitted"] is False


def test_buildercodes_default_keeps_s63a_intent_shape() -> None:
    intent = _intent(Settings())
    # The S6.3a default intent shape is unchanged (no new keys, builder absent).
    assert set(intent) == {
        "market",
        "ownerAddress",
        "subaccountNumber",
        "clientId",
        "side",
        "orderType",
        "size",
        "price",
        "quantums",
        "subticks",
        "timeInForce",
        "reduceOnly",
        "goodTilBlock",
        "goodTilBlockTime",
        "builderCodeParameters",
        "requiresClientSignature",
        "submitted",
    }
    assert intent["builderCodeParameters"] is None
    assert intent["submitted"] is False
