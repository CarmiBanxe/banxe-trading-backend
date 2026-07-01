"""S6.4-EN Phase-2c — complex offline conformance for the CANCEL / STATUS lifecycle.

Companion to ``test_dydx_route_conformance.py`` (#64). That suite exhaustively
covers the **PLACE** surface (POST /api/v1/orders) under the 2^5 route gate.
This suite covers the remaining ExchangePort operations that route through the
same S6.4-EN gate but were NOT exercised end-to-end via HTTP:

  1. DELETE /api/v1/orders/{id} under the FULL 2^5 truth table — the CANCEL
     surface honours the same route gate as PLACE (exactly one all-true combo
     dispatches to the dydx adapter; the other 31 fail-closed to the mock).
  2. GET /api/v1/orders/{id} under the FULL 2^5 truth table — STATUS is still
     Indexer-gated (S6.3b) on the dydx adapter, so the LIVE route MUST map
     ``ExchangeUnavailable`` to HTTP 503 (§D3), while the mock route returns
     an ACCEPTED OrderResult.
  3. CANCEL idempotency / replay via HTTP on BOTH routes — repeated DELETE
     of the same id returns the same shape and never touches the submission
     transport (autouse fixture asserts this by raising on touch).
  4. NO-transport guard active for the whole lifecycle — an operator-armed
     ``submit_signed_order`` (submit_enabled=True + valid node URL) still
     stops at the fake transport fence and maps to §D3 ExchangeUnavailable,
     proving the RED-zone belt-and-suspenders: even the operator path never
     opens a socket in CI.
  5. Multi-market place-intent determinism — BTC-USD (atomic_resolution -10)
     and ETH-USD (-9) each yield deterministic atomic-integer STRINGS on the
     unsigned intent. The existing suite only asserts BTC.
  6. Cancel-intent shape is market-agnostic — build_cancel_intent produces
     the same self-custodial UNSIGNED shape regardless of the id / market.
  7. Cross-cutting E2E lifecycle on the mock route — place → status → cancel
     → status, all 200, response bodies carry NO signature/key (deny-list).
  8. Signed-order HTTP surface fencing — no endpoint accepts a client-signed
     order body (surplus/signature-like fields are dropped by the pydantic
     wire model), and the place path is safe against a spoofed signed body.

**RED-zone** invariants (all hard-asserted):

* NO mainnet, NO real funds, NO real keys.
* NO live network in CI: an autouse fixture monkeypatches
  ``httpx.AsyncClient`` **and** ``HttpxSubmissionTransport.submit`` to raise
  ``_ForbiddenNetworkCall``. Any attempt to open a socket or call the live
  submission transport instantly fails the offending test.
* NO transport arming: only obviously-fake placeholders and the existing
  ``0x11*32`` SIWE test key are used. The kill-switch remains OFF in every
  DEFAULT-shaped test; the FULL-combo tests use an ``.invalid`` node URL.
* TESTS-ONLY: no src/ change. If a test would surface a real bug it is
  reported (not patched) — none does; this file exercises exactly the seams
  already shipped by PR #63.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from decimal import Decimal
from typing import Any

import httpx
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.dse import (
    DYDX_EXCHANGE_PROVIDER,
    resolve_exchange_route,
)
from banxe_trading_backend.models import (
    ExchangeOrderRequest,
    OrderSide,
    OrderType,
)
from banxe_trading_backend.ports import (
    DydxExchangeAdapter,
    ExchangeUnavailable,
    HttpxSubmissionTransport,
    InMemoryMockExchange,
)
from banxe_trading_backend.ports.dydx_exchange import (
    _DEFAULT_MARKETS,
    calculate_quantums,
    calculate_subticks,
)
from banxe_trading_backend.services.order_controls import HITL_HEADER

# --------------------------------------------------------------------------- #
# Fixtures & fakes (mirror test_dydx_route_conformance.py so both suites      #
# reuse the same RED-zone convention)                                          #
# --------------------------------------------------------------------------- #

# Obviously-fake testnet placeholder — NOT a real endpoint. Tests only.
FAKE_TESTNET_NODE_URL = "https://example-dydx-testnet-node.invalid"

# SIWE test key (mirrors tests/test_dydx_route_conformance.py; obviously-fake).
SIWE_TEST_KEY = "0x" + "11" * 32

# FULL S6.4-EN combo — every flag/URL required to select the dydx live route.
FULL_COMBO: dict[str, Any] = {
    "exchange_provider": "dydx",
    "dse_provider_mode": "sandbox-live",
    "dse_live_allowed": True,
    "dydx_submit_enabled": True,
    "dydx_node_url": FAKE_TESTNET_NODE_URL,
}

_GATE_FLAGS: dict[str, tuple[Any, Any]] = {
    "exchange_provider": ("dydx", "mock"),
    "dse_provider_mode": ("sandbox-live", "mock"),
    "dse_live_allowed": (True, False),
    "dydx_submit_enabled": (True, False),
    "dydx_node_url": (FAKE_TESTNET_NODE_URL, None),
}
_GATE_ORDER: tuple[str, ...] = tuple(_GATE_FLAGS.keys())
_ALL_TRUE_MASK: int = (1 << len(_GATE_FLAGS)) - 1  # 0b11111 == 31


def _combo(mask: int) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for bit, name in enumerate(_GATE_ORDER):
        true_v, false_v = _GATE_FLAGS[name]
        kwargs[name] = true_v if mask & (1 << bit) else false_v
    return kwargs


def _mask_id(mask: int) -> str:
    bits = "".join("T" if mask & (1 << i) else "F" for i in range(len(_GATE_ORDER)))
    return f"m{mask:02d}_{bits}"


def _siwe_session(client: TestClient, key: str = SIWE_TEST_KEY) -> tuple[str, str]:
    """Sign in via SIWE and return ``(address, session_token)``."""
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
    return address, token


def _order_body(client_order_id: str, correlation_id: str) -> dict[str, Any]:
    return {
        "symbol": "BTC-USD",
        "side": "buy",
        "type": "limit",
        "amount": "0.5",
        "limitPrice": "67000",
        "clientOrderId": client_order_id,
        "correlationId": correlation_id,
    }


# --------------------------------------------------------------------------- #
# Autouse — RED-zone no-live-network guard (raises on any transport touch)   #
# --------------------------------------------------------------------------- #


class _ForbiddenNetworkCall(RuntimeError):
    """Raised if a test in this suite touches the live submission transport."""


@pytest.fixture(autouse=True)
def _no_live_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail HARD if a test opens ``httpx.AsyncClient`` OR calls the live dydx
    submission transport. The lifecycle path (PLACE / DELETE / GET) must never
    invoke ``HttpxSubmissionTransport.submit``; the TestClient uses an in-process
    ASGI transport (starlette) which does not construct ``httpx.AsyncClient``.
    """

    def _blocked_async_client(*args: Any, **kwargs: Any) -> Any:
        raise _ForbiddenNetworkCall(
            "httpx.AsyncClient is forbidden in this suite (RED-zone: no live network)"
        )

    async def _blocked_submit(
        self: HttpxSubmissionTransport,
        node_url: str,
        signed_order: Mapping[str, object],
        *,
        timeout_s: float,
    ) -> Mapping[str, object]:
        raise _ForbiddenNetworkCall(
            "HttpxSubmissionTransport.submit is forbidden in this suite "
            "(lifecycle path must never invoke live submission transport)"
        )

    monkeypatch.setattr(httpx, "AsyncClient", _blocked_async_client)
    monkeypatch.setattr(HttpxSubmissionTransport, "submit", _blocked_submit)
    yield


# --------------------------------------------------------------------------- #
# Self-custody deny-list scanner (mirrors the primary conformance suite)     #
# --------------------------------------------------------------------------- #


_FORBIDDEN_KEY_SUBSTRINGS = (
    "signature",
    "signedtx",
    "signedtransaction",
    "privatekey",
    "secret",
    "mnemonic",
    "seedphrase",
    "apikey",
)


def _assert_no_forbidden_fields(payload: object, path: str = "$") -> None:
    """Walk any JSON-like payload; reject signature/key-shaped keys.

    ``requiresClientSignature`` is a BOOLEAN safelist entry — it tells the
    client wallet to sign, never a signature value.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = key.lower().replace("_", "").replace("-", "")
            for forbidden in _FORBIDDEN_KEY_SUBSTRINGS:
                if forbidden in lowered and lowered != "requiresclientsignature":
                    raise AssertionError(
                        f"forbidden key '{key}' at {path} (matched '{forbidden}')"
                    )
            _assert_no_forbidden_fields(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            _assert_no_forbidden_fields(item, f"{path}[{i}]")


# --------------------------------------------------------------------------- #
# 1. FULL 2^5 truth-table on the CANCEL surface (DELETE /orders/{id})        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "mask", list(range(2 ** len(_GATE_FLAGS))), ids=_mask_id
)
def test_cancel_surface_truth_table_routes_match_place_route(mask: int) -> None:
    """DELETE /orders/{id} honours the SAME S6.4-EN gate as PLACE.

    - all-true combo (mask == 31) → dydx adapter's ``cancel_order`` runs, which
      builds an unsigned cancel intent and returns ``cancelled=True``. NO
      submission transport is touched (the autouse fixture asserts this).
    - any other combo → in-memory mock ``cancel_order`` runs; an unknown
      order id is idempotently rejected (``cancelled=False``) with no error.
    """
    kwargs = _combo(mask)
    app = create_app(Settings(**kwargs))
    # Belt-and-suspenders: the resolved app-level route agrees with the resolver.
    if mask == _ALL_TRUE_MASK:
        assert app.state.exchange_route == DYDX_EXCHANGE_PROVIDER, kwargs
        assert isinstance(app.state.exchange, DydxExchangeAdapter), kwargs
    else:
        assert app.state.exchange_route == "mock", kwargs
        assert isinstance(app.state.exchange, InMemoryMockExchange), kwargs

    client = TestClient(app)
    resp = client.delete("/api/v1/orders/lifecycle-cancel-id")
    assert resp.status_code == 200, (mask, resp.text)
    body = resp.json()
    assert body["orderId"] == "lifecycle-cancel-id"
    if mask == _ALL_TRUE_MASK:
        # dydx cancel_order builds the intent (validates constructibility) and
        # returns True — the client wallet is responsible for signing/submitting.
        assert body["cancelled"] is True, kwargs
    else:
        # mock cancel_order: id not present in the empty registry → False.
        assert body["cancelled"] is False, kwargs
    _assert_no_forbidden_fields(body)


# --------------------------------------------------------------------------- #
# 2. FULL 2^5 truth-table on the STATUS surface (GET /orders/{id})           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "mask", list(range(2 ** len(_GATE_FLAGS))), ids=_mask_id
)
def test_status_surface_truth_table_maps_gate_to_d3(mask: int) -> None:
    """GET /orders/{id} honours the SAME gate as PLACE and maps §D3 to HTTP.

    - all-true combo → dydx ``get_order_status`` raises ``ExchangeUnavailable``
      (still Indexer-gated in S6.3b); the router's ``ExchangeError`` handler
      maps that to HTTP 503, and no transport is touched.
    - any other combo → in-memory mock returns an ACCEPTED OrderResult 200.
    """
    kwargs = _combo(mask)
    client = TestClient(create_app(Settings(**kwargs)))
    resp = client.get("/api/v1/orders/lifecycle-status-id")
    if mask == _ALL_TRUE_MASK:
        # §D3: ExchangeUnavailable → 503 (dYdX status still Indexer-gated).
        assert resp.status_code == 503, (kwargs, resp.text)
        detail = resp.json()["detail"].lower()
        # The message must reference the dydx/Indexer gate; never a signature/key.
        assert "dydx" in detail or "indexer" in detail
    else:
        assert resp.status_code == 200, (kwargs, resp.text)
        body = resp.json()
        assert body["orderId"] == "lifecycle-status-id"
        assert body["state"] == "accepted"
        _assert_no_forbidden_fields(body)


# --------------------------------------------------------------------------- #
# 3. CANCEL idempotency / replay via HTTP on both routes                     #
# --------------------------------------------------------------------------- #


def test_mock_cancel_replay_via_http_is_idempotent() -> None:
    """Replayed DELETE returns the same shape on the mock route (unknown id)."""
    client = TestClient(create_app(Settings()))
    first = client.delete("/api/v1/orders/replay-mock-id").json()
    second = client.delete("/api/v1/orders/replay-mock-id").json()
    third = client.delete("/api/v1/orders/replay-mock-id").json()
    assert first == second == third
    assert first == {"orderId": "replay-mock-id", "cancelled": False}


def test_dydx_cancel_replay_via_http_is_idempotent_and_no_transport() -> None:
    """Replayed DELETE on the live route returns the same shape and never
    invokes the submission transport (the autouse fixture would raise).
    """
    client = TestClient(create_app(Settings(**FULL_COMBO)))
    first = client.delete("/api/v1/orders/replay-dydx-id").json()
    second = client.delete("/api/v1/orders/replay-dydx-id").json()
    assert first == second == {"orderId": "replay-dydx-id", "cancelled": True}


def test_mock_cancel_of_known_order_returns_true_and_deny_list_clean() -> None:
    """Place then DELETE on the mock route: cancel of a KNOWN id returns True."""
    client = TestClient(create_app(Settings()))
    place = client.post(
        "/api/v1/orders", json=_order_body("c-mock-known", "r-mock-known")
    )
    assert place.status_code == 200
    order_id = place.json()["orderId"]
    cancelled = client.delete(f"/api/v1/orders/{order_id}").json()
    assert cancelled == {"orderId": order_id, "cancelled": True}
    _assert_no_forbidden_fields(cancelled)


# --------------------------------------------------------------------------- #
# 4. NO-transport guard — operator-armed submit_signed_order stays fenced    #
# --------------------------------------------------------------------------- #


def test_operator_armed_submit_signed_order_is_still_fenced_in_ci() -> None:
    """Even when the operator has opened the submission gate (flag + valid
    URL), the injected ``HttpxSubmissionTransport`` cannot open a socket in
    CI — the autouse fixture patches ``submit`` to raise ``_ForbiddenNetworkCall``.
    The adapter maps that failure to §D3 ``ExchangeUnavailable``.
    """
    adapter = DydxExchangeAdapter.from_settings(
        Settings(dydx_submit_enabled=True, dydx_node_url=FAKE_TESTNET_NODE_URL)
    )
    assert adapter.submission_enabled() is True
    with pytest.raises(ExchangeUnavailable, match="submission failed"):
        asyncio.run(adapter.submit_signed_order({"signed": "tx"}))


def test_lifecycle_httpx_async_client_is_forbidden() -> None:
    """Meta-test: any direct ``httpx.AsyncClient`` construction raises."""
    with pytest.raises(_ForbiddenNetworkCall):
        httpx.AsyncClient()


# --------------------------------------------------------------------------- #
# 5. Multi-market place-intent determinism (BTC-USD vs ETH-USD)              #
# --------------------------------------------------------------------------- #


def test_multi_market_defaults_have_distinct_quantization_params() -> None:
    """BTC-USD and ETH-USD ship with distinct market params — a determinism
    baseline against silent copy-paste (both quantum params must differ).
    """
    btc = _DEFAULT_MARKETS["BTC-USD"]
    eth = _DEFAULT_MARKETS["ETH-USD"]
    assert btc.atomic_resolution == -10
    assert eth.atomic_resolution == -9
    # Same subticks_per_tick / step_base_quantums for the MVP defaults, but the
    # atomic_resolution difference is what drives quantum scale per market.
    assert btc.atomic_resolution != eth.atomic_resolution


@pytest.mark.parametrize(
    ("size", "expected_btc_quantums", "expected_eth_quantums"),
    [
        ("1", 10_000_000_000, 1_000_000_000),
        ("0.5", 5_000_000_000, 500_000_000),
        ("0.001", 10_000_000, 1_000_000),
    ],
)
def test_multi_market_quantums_are_integer_exact_per_market(
    size: str, expected_btc_quantums: int, expected_eth_quantums: int
) -> None:
    """Decimal-exact quantum math per market — no float taint, per I-01."""
    btc = _DEFAULT_MARKETS["BTC-USD"]
    eth = _DEFAULT_MARKETS["ETH-USD"]
    assert calculate_quantums(Decimal(size), btc) == expected_btc_quantums
    assert calculate_quantums(Decimal(size), eth) == expected_eth_quantums


def test_multi_market_subticks_are_integer_exact() -> None:
    """Subtick math is integer-exact per market — quote atomic resolution -6
    is fixed by dYdX; the delta comes from atomic_resolution vs quantum_exponent.
    """
    btc = _DEFAULT_MARKETS["BTC-USD"]
    eth = _DEFAULT_MARKETS["ETH-USD"]
    # 67000 * 10^(-10 - (-9) - (-6)) = 67000 * 10^5 → 6_700_000_000, ticked to 1e5.
    assert calculate_subticks(Decimal("67000"), btc) == 6_700_000_000
    # 3500 * 10^(-9 - (-9) - (-6)) = 3500 * 10^6 → 3_500_000_000.
    assert calculate_subticks(Decimal("3500"), eth) == 3_500_000_000


def _dydx_place_intent(symbol: str, size: str, price: str) -> dict[str, object]:
    base, _, quote = symbol.partition("-")
    order = ExchangeOrderRequest(
        base_asset=base,
        quote_asset=quote,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        amount=size,
        client_order_id=f"multi-{symbol}-{size}",
        correlation_id=f"corr-multi-{symbol}",
        limit_price=price,
        owner_address="0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A",
    )
    return DydxExchangeAdapter().build_place_intent(order)


def test_multi_market_place_intents_are_deterministic_and_integer_strings() -> None:
    """BTC-USD and ETH-USD intents both carry integer STRINGS for atomic units
    (I-01), and identical inputs → identical intents across two invocations.
    """
    btc_a = _dydx_place_intent("BTC-USD", "0.5", "67000")
    btc_b = _dydx_place_intent("BTC-USD", "0.5", "67000")
    eth_a = _dydx_place_intent("ETH-USD", "1", "3500")
    eth_b = _dydx_place_intent("ETH-USD", "1", "3500")

    assert btc_a == btc_b, "identical inputs must yield identical BTC intents"
    assert eth_a == eth_b, "identical inputs must yield identical ETH intents"
    # BTC-USD intent shape.
    assert btc_a["market"] == "BTC-USD"
    assert isinstance(btc_a["quantums"], str) and btc_a["quantums"] == "5000000000"
    assert isinstance(btc_a["subticks"], str) and btc_a["subticks"] == "6700000000"
    # ETH-USD intent shape.
    assert eth_a["market"] == "ETH-USD"
    assert isinstance(eth_a["quantums"], str) and eth_a["quantums"] == "1000000000"
    assert isinstance(eth_a["subticks"], str) and eth_a["subticks"] == "3500000000"
    # Cross-market intents must NOT collide (distinct market → distinct clientId
    # bucket is expected only when clientOrderId also differs — here we assert
    # market fields differ, which is the invariant).
    assert btc_a["market"] != eth_a["market"]
    for intent in (btc_a, eth_a):
        _assert_no_forbidden_fields(intent)


# --------------------------------------------------------------------------- #
# 6. Cancel-intent shape is market-agnostic                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "order_id",
    ["order-btc", "order-eth", "mock-000042", "not-a-real-order", "with/slash"],
)
def test_cancel_intent_is_market_agnostic_and_self_custodial(order_id: str) -> None:
    """``build_cancel_intent`` takes only an id — the shape is identical for
    every id and never carries a signature/key. Self-custodial by construction.
    """
    intent = DydxExchangeAdapter().build_cancel_intent(order_id)
    assert set(intent) == {
        "ordersToCancel",
        "subaccountNumber",
        "goodTilBlock",
        "requiresClientSignature",
        "submitted",
    }
    assert intent["ordersToCancel"] == [order_id]
    assert intent["submitted"] is False
    assert intent["requiresClientSignature"] is True
    _assert_no_forbidden_fields(intent)


# --------------------------------------------------------------------------- #
# 7. Cross-cutting E2E lifecycle on the mock route (place → status → cancel) #
# --------------------------------------------------------------------------- #


def test_mock_route_full_lifecycle_place_status_cancel_no_transport() -> None:
    """Place → status → cancel → status on the MOCK route.

    All hops return 200; the autouse fixture guarantees no transport is
    touched; every response body passes the self-custody deny-list scan.
    """
    client = TestClient(create_app(Settings()))
    body = _order_body("c-lifecycle-full", "r-lifecycle-full")

    place = client.post("/api/v1/orders", json=body)
    assert place.status_code == 200
    place_body = place.json()
    _assert_no_forbidden_fields(place_body)
    order_id = place_body["orderId"]
    assert order_id == "mock-000001"

    status = client.get(f"/api/v1/orders/{order_id}")
    assert status.status_code == 200
    _assert_no_forbidden_fields(status.json())

    cancelled = client.delete(f"/api/v1/orders/{order_id}")
    assert cancelled.status_code == 200
    cancel_body = cancelled.json()
    _assert_no_forbidden_fields(cancel_body)
    assert cancel_body == {"orderId": order_id, "cancelled": True}

    # The mock is stateless on cancel (§D3 idempotency): status stays 200 after.
    status_after = client.get(f"/api/v1/orders/{order_id}")
    assert status_after.status_code == 200


def test_dydx_route_lifecycle_place_yields_unsigned_intent_and_cancel_ok() -> None:
    """Live route: SIWE-authenticated place → cancel via HTTP.

    Place returns an unsigned intent (submitted:false); cancel returns
    cancelled:True after building the unsigned cancel intent. No transport
    is invoked on either hop — the RED-zone fence is asserted transitively.
    """
    client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
    _, token = _siwe_session(client)

    place = client.post(
        "/api/v1/orders",
        json=_order_body("c-live-lc", "r-live-lc"),
        headers={"Authorization": f"Bearer {token}", HITL_HEADER: "true"},
    )
    assert place.status_code == 200
    place_body = place.json()
    _assert_no_forbidden_fields(place_body)
    assert place_body["raw"]["submitted"] is False
    assert place_body["raw"]["requiresClientSignature"] is True

    cancelled = client.delete(
        f"/api/v1/orders/{place_body['orderId']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancelled.status_code == 200
    cancel_body = cancelled.json()
    _assert_no_forbidden_fields(cancel_body)
    assert cancel_body["cancelled"] is True


# --------------------------------------------------------------------------- #
# 8. Signed-order HTTP surface fencing (extra fields must be dropped)        #
# --------------------------------------------------------------------------- #


def test_place_body_with_spoofed_signature_field_is_silently_dropped() -> None:
    """The place surface accepts only the shipped ``PlaceOrderRequest`` shape;
    any extra ``signature`` / ``signedTx`` / ``privateKey`` field a caller
    might attach is dropped by pydantic (``extra='ignore'`` on ``CamelModel``
    defaults) and CANNOT sneak into the ExchangePort call.

    Positive assertion: the response is a normal 200 with no signature-like
    field anywhere in the body — proving the ExchangePort surface never
    exposes an accepted-signed-order path.
    """
    client = TestClient(create_app(Settings()))
    body: dict[str, Any] = {
        **_order_body("c-spoof", "r-spoof"),
        # These extra fields must be ignored by the wire model, not persisted.
        "signature": "0xdeadbeef",
        "signedTx": {"payload": "bogus"},
        "privateKey": "0xnope",
        "apiKey": "should-not-exist",
    }
    resp = client.post("/api/v1/orders", json=body)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    # No signature-like echo in the response. The order MUST have been placed
    # via the unsigned path (mock route → orderId prefix "mock-").
    _assert_no_forbidden_fields(payload)
    assert payload["orderId"].startswith("mock-")


def test_no_route_is_a_signed_submission_endpoint() -> None:
    """Enumerate the FastAPI route table — no path exposes a signed-submission
    endpoint. Any future ``/submit`` / ``/signed`` route would ship a signed
    payload; this suite ensures the fence stays whole.
    """
    app = create_app(Settings())
    for route in app.router.routes:
        path = str(getattr(route, "path", ""))
        lowered = path.lower()
        assert "/submit" not in lowered, f"unexpected signed-submission path: {path}"
        assert "/signed" not in lowered, f"unexpected signed-submission path: {path}"


# --------------------------------------------------------------------------- #
# 9. Belt-and-suspenders — resolver agrees on the LIFECYCLE gate too         #
# --------------------------------------------------------------------------- #


def test_resolver_agrees_with_lifecycle_gate() -> None:
    """The single-source resolver returns dydx iff EVERY gate flag is on.

    A separate belt for the CANCEL/STATUS parametrised suites: their pass
    condition depends on ``resolve_exchange_route`` matching the app-state
    route, so the resolver must be exactly-one-live over all 32 combos.
    """
    live = [
        mask
        for mask in range(2 ** len(_GATE_FLAGS))
        if resolve_exchange_route(Settings(**_combo(mask))) == DYDX_EXCHANGE_PROVIDER
    ]
    assert live == [_ALL_TRUE_MASK], (
        f"expected exactly one live combo (all-true); got masks {live}"
    )
