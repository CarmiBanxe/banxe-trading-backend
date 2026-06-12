"""dYdX ExchangePort adapter — UNSIGNED intent construction (ADR-083 S6.3a).

No network, no keys, no chain. Tests the reversible execution-construction:
quantum/subtick Decimal math (I-01), market/limit/cancel intents, TIF/reduce-only,
Builder Codes gating, §D3 error→HTTP mapping, and auth-required gating.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.models import (
    ExchangeOrderRequest,
    OrderSide,
    OrderType,
    TimeInForce,
)
from banxe_trading_backend.ports import (
    BuilderCodes,
    ComplianceBlock,
    DydxExchangeAdapter,
    ExchangePort,
    ExchangeUnavailable,
    InsufficientBalance,
    StaleRate,
    ValidationError,
    calculate_quantums,
    calculate_subticks,
)
from banxe_trading_backend.ports.dydx_exchange import DydxMarketParams

BTC = DydxMarketParams("BTC-USD", -10, -9, 1_000_000, 100_000)


def order(**kw: object) -> ExchangeOrderRequest:
    base = {
        "base_asset": "BTC",
        "quote_asset": "USD",
        "side": OrderSide.BUY,
        "type": OrderType.LIMIT,
        "amount": "0.5",
        "client_order_id": "coid-1",
        "correlation_id": "corr-1",
        "limit_price": "67000",
        "owner_address": "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A",
    }
    base.update(kw)
    return ExchangeOrderRequest(**base)  # type: ignore[arg-type]


# --------------------------- quantum/subtick math --------------------------- #


def test_quantum_subtick_math_is_decimal_exact() -> None:
    # 0.5 BTC * 10^10 = 5e9, rounded to step 1e6 → 5_000_000_000
    assert calculate_quantums(Decimal("0.5"), BTC) == 5_000_000_000
    # 67000 * 10^5 = 6.7e9, rounded to tick 1e5 → 6_700_000_000
    assert calculate_subticks(Decimal("67000"), BTC) == 6_700_000_000
    # Sub-step size is rounded down then floored to the minimum step (never 0).
    assert calculate_quantums(Decimal("0.00000001"), BTC) == 1_000_000


# --------------------------- intent construction ---------------------------- #


def test_limit_intent_has_quantums_subticks_and_gtt() -> None:
    intent = DydxExchangeAdapter().build_place_intent(order())
    assert intent["market"] == "BTC-USD"
    assert intent["side"] == "BUY"
    assert intent["orderType"] == "LIMIT"
    assert intent["quantums"] == "5000000000"  # atomic integer string (I-01)
    assert intent["subticks"] == "6700000000"
    assert intent["price"] == "67000"
    assert intent["timeInForce"] == "GTT"
    assert intent["reduceOnly"] is False
    assert intent["requiresClientSignature"] is True
    assert intent["submitted"] is False
    assert intent["builderCodeParameters"] is None  # gated/no-op default


def test_market_intent_has_no_subticks_and_ioc_default() -> None:
    intent = DydxExchangeAdapter().build_place_intent(
        order(type=OrderType.MARKET, limit_price=None)
    )
    assert intent["orderType"] == "MARKET"
    assert intent["quantums"] == "5000000000"
    assert intent["subticks"] is None  # slippage bound supplied client-side
    assert intent["timeInForce"] == "IOC"


def test_side_reduce_only_and_tif_override() -> None:
    intent = DydxExchangeAdapter().build_place_intent(
        order(side=OrderSide.SELL, reduce_only=True, time_in_force=TimeInForce.POST_ONLY)
    )
    assert intent["side"] == "SELL"
    assert intent["reduceOnly"] is True
    assert intent["timeInForce"] == "POST_ONLY"


def test_builder_codes_attached_only_when_configured() -> None:
    with_codes = DydxExchangeAdapter(builder_codes=BuilderCodes("0xBUILDER", 50))
    intent = with_codes.build_place_intent(order())
    assert intent["builderCodeParameters"] == {"builderAddress": "0xBUILDER", "feePpm": 50}


def test_builder_codes_default_from_settings_is_noop() -> None:
    # Default settings carry no builder address → no builder params attached.
    adapter = DydxExchangeAdapter.from_settings(Settings())
    assert adapter.build_place_intent(order())["builderCodeParameters"] is None


def test_cancel_intent_is_unsigned_and_unsubmitted() -> None:
    intent = DydxExchangeAdapter().build_cancel_intent("order-xyz")
    assert intent["ordersToCancel"] == ["order-xyz"]
    assert intent["requiresClientSignature"] is True
    assert intent["submitted"] is False


def test_place_order_returns_unsigned_intent_in_raw() -> None:
    result = asyncio.run(DydxExchangeAdapter().place_order(order()))
    assert result.raw is not None
    assert result.raw["submitted"] is False
    intent = result.raw["unsignedIntent"]
    assert isinstance(intent, dict)
    assert intent["quantums"] == "5000000000"


# --------------------------- validation / errors ---------------------------- #


def test_adapter_satisfies_exchangeport_protocol() -> None:
    assert isinstance(DydxExchangeAdapter(), ExchangePort)


def test_unknown_market_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        DydxExchangeAdapter().build_place_intent(order(base_asset="DOGE", quote_asset="USD"))


def test_missing_owner_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        DydxExchangeAdapter().build_place_intent(order(owner_address=None))


def test_limit_without_price_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        DydxExchangeAdapter().build_place_intent(order(limit_price=None))


def test_non_positive_size_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        DydxExchangeAdapter().build_place_intent(order(amount="0"))


def test_status_and_rate_are_gated_to_s63b() -> None:
    adapter = DydxExchangeAdapter()
    with pytest.raises(ExchangeUnavailable):
        asyncio.run(adapter.get_order_status("x"))
    with pytest.raises(ExchangeUnavailable):
        asyncio.run(adapter.get_rate("BTC", "USD"))


def test_d3_error_model_http_status_mapping() -> None:
    assert ValidationError().http_status == 400
    assert StaleRate().http_status == 409
    assert ExchangeUnavailable().http_status == 503
    assert InsufficientBalance().http_status == 402
    assert ComplianceBlock().http_status == 451


# --------------------------- router (dydx provider) ------------------------- #


def _dydx_client(**settings: object) -> TestClient:
    return TestClient(create_app(Settings(exchange_provider="dydx", **settings)))


def test_router_maps_exchange_unavailable_to_503() -> None:
    resp = _dydx_client().get("/api/v1/orders/some-id")
    assert resp.status_code == 503


def test_router_maps_validation_error_to_400() -> None:
    # No auth → owner None → adapter raises ValidationError → 400.
    body = {
        "symbol": "BTC-USD",
        "side": "buy",
        "type": "limit",
        "amount": "0.5",
        "limitPrice": "67000",
        "clientOrderId": "c1",
        "correlationId": "r1",
    }
    resp = _dydx_client().post("/api/v1/orders", json=body)
    assert resp.status_code == 400


# --------------------------- auth-required gating --------------------------- #


def test_order_requires_session_when_auth_enabled() -> None:
    body = {
        "symbol": "BTC-USD",
        "side": "buy",
        "type": "limit",
        "amount": "0.5",
        "limitPrice": "67000",
        "clientOrderId": "c1",
        "correlationId": "r1",
    }
    resp = _dydx_client(auth_enabled=True).post("/api/v1/orders", json=body)
    assert resp.status_code == 401  # no wallet session


def test_authenticated_order_returns_unsigned_intent() -> None:
    client = _dydx_client(auth_enabled=True)
    key = "0x" + "11" * 32
    address = Account.from_key(key).address

    nonce = client.get("/api/v1/auth/nonce").json()["nonce"]
    message = "\n".join(
        [
            "localhost wants you to sign in with your Ethereum account:",
            address,
            "",
            "URI: https://localhost",
            "Version: 1",
            "Chain ID: 1",
            f"Nonce: {nonce}",
            "Issued At: 2026-06-12T00:00:00Z",
        ]
    )
    signature = "0x" + Account.sign_message(
        encode_defunct(text=message), private_key=key
    ).signature.hex().removeprefix("0x")
    token = client.post(
        "/api/v1/auth/verify", json={"message": message, "signature": signature}
    ).json()["token"]

    resp = client.post(
        "/api/v1/orders",
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "type": "limit",
            "amount": "0.5",
            "limitPrice": "67000",
            "clientOrderId": "c-auth",
            "correlationId": "r-auth",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    raw = resp.json()["raw"]
    assert raw["submitted"] is False
    assert raw["unsignedIntent"]["ownerAddress"].lower() == address.lower()
    assert raw["unsignedIntent"]["quantums"] == "5000000000"
