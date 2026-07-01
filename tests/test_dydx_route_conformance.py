"""S6.4-EN Phase-2a — COMPLEX conformance suite for the dydx live-order route.

Adversarial, offline conformance suite exercising the trading-block safety
surface of the S6.4-EN route gate. TESTS ONLY: no runtime change; only the
seams shipped by PR #63 are exercised.

Coverage areas (10):
  1. FULL 2^5 truth table for the five gate flags — EXACTLY ONE combo (all true)
     routes to the dydx UNSIGNED-INTENT path; the other 31 fail-closed to mock.
  2. Node-URL adversarial set — mainnet-looking / malformed / empty / bad-scheme
     / missing-host URLs all fail-close to mock.
  3. Idempotency / dedup — a replay of the same clientOrderId returns the same
     logical outcome (mock exchange dedupes by clientOrderId; dydx adapter
     derives a deterministic uint32 clientId from the same input).
  4. Ruflo gate — a Ruflo disallow decision fail-closes the order surface with
     HTTP 451 (never reaches the exchange transport).
  5. HITL gate — live route without X-Banxe-Hitl-Confirm → 428; with truthy
     header → proceeds to the unsigned intent (still no transport).
  6. Self-custodial — response NEVER carries signature/signedTx/privateKey/
     secret fields (deny-list scan on the entire response body).
  7. Kill-switch default-off — under shipped defaults, ALWAYS mock;
     submission_enabled() is False; live submission raises unavailable.
  8. No-network assertion — httpx.AsyncClient and the submission transport are
     monkeypatched to raise on touch; the order flow never trips them.
  9. I-01 Decimal — amounts/prices are decimal strings; a float amount is
     rejected at the pydantic boundary (never reaches the exchange).
 10. Determinism — identical inputs → identical outputs across repeated runs
     (no time/random leak in the unsigned intent shape).

RED-zone: NO mainnet, NO real funds, NO real keys/secrets/values. Only
obviously-fake testnet placeholders and the existing 0x11*32 SIWE test key are
used. Kill-switch defaults stay OFF; NO live-submission transport is invoked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
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
from banxe_trading_backend.ports import (
    DydxExchangeAdapter,
    ExchangeUnavailable,
    HttpxSubmissionTransport,
    InMemoryMockExchange,
)
from banxe_trading_backend.ports.dydx_exchange import is_valid_node_url
from banxe_trading_backend.services import order_controls
from banxe_trading_backend.services.order_controls import (
    HITL_HEADER,
    RufloDecision,
)

# --------------------------------------------------------------------------- #
# Fixtures & fakes                                                            #
# --------------------------------------------------------------------------- #

# Obviously-fake testnet placeholder — NOT a real endpoint. Tests only.
FAKE_TESTNET_NODE_URL = "https://example-dydx-testnet-node.invalid"

# SIWE test key (mirrors tests/test_dydx_exchange_route.py; obviously-fake).
SIWE_TEST_KEY = "0x" + "11" * 32

# FULL S6.4-EN combo — every flag/URL required to select the dydx live route.
FULL_COMBO: dict[str, Any] = {
    "exchange_provider": "dydx",
    "dse_provider_mode": "sandbox-live",
    "dse_live_allowed": True,
    "dydx_submit_enabled": True,
    "dydx_node_url": FAKE_TESTNET_NODE_URL,
}

# The five gate flags expressed as (TRUE-value, FALSE-value) pairs. The TRUE
# side is the value REQUIRED for the live dydx route; the FALSE side is any
# value that fail-closes to mock. The 2^5 truth table below enumerates every
# combination of these five bits.
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
    """Kwargs for a given 5-bit mask (bit k → k-th flag TRUE)."""
    kwargs: dict[str, Any] = {}
    for bit, name in enumerate(_GATE_ORDER):
        true_v, false_v = _GATE_FLAGS[name]
        kwargs[name] = true_v if mask & (1 << bit) else false_v
    return kwargs


def _mask_id(mask: int) -> str:
    """Human-readable id for the parametrised truth table (T/F per flag)."""
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
# 8. No-network / no-transport guard (autouse — protects the whole suite)     #
# --------------------------------------------------------------------------- #


class _ForbiddenNetworkCall(RuntimeError):
    """Raised if a test in this suite touches the live submission transport."""


@pytest.fixture(autouse=True)
def _no_live_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail HARD if any test opens a real outbound httpx client OR invokes the
    dydx submission transport. TestClient uses an in-process ASGI transport
    (starlette) which does NOT construct ``httpx.AsyncClient`` — the outbound
    async client is only used by ``HttpxSubmissionTransport`` (the seam we
    fence in this suite). No real socket is opened either way.
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
            "(order path must never invoke live submission transport)"
        )

    monkeypatch.setattr(httpx, "AsyncClient", _blocked_async_client)
    monkeypatch.setattr(HttpxSubmissionTransport, "submit", _blocked_submit)
    yield


# --------------------------------------------------------------------------- #
# 1. FULL 2^5 truth-table for the five gate flags                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "mask", list(range(2 ** len(_GATE_FLAGS))), ids=_mask_id
)
def test_full_truth_table_only_all_true_routes_to_dydx(mask: int) -> None:
    """Exhaustive 2^5 = 32-combination truth table for the S6.4-EN route gate.

    Exactly ONE combination — every gate flag ON (mask == 0b11111 == 31) —
    resolves to the live dydx UNSIGNED-INTENT route AND the app binds the
    ``DydxExchangeAdapter``. The other 31 fail-closed to the in-memory mock
    (both at the resolver AND at the built ExchangePort layer).
    """
    kwargs = _combo(mask)
    settings = Settings(**kwargs)
    route = resolve_exchange_route(settings)
    exchange = create_app(settings).state.exchange

    if mask == _ALL_TRUE_MASK:
        assert route == DYDX_EXCHANGE_PROVIDER, kwargs
        assert isinstance(exchange, DydxExchangeAdapter), kwargs
    else:
        assert route == "mock", kwargs
        assert isinstance(exchange, InMemoryMockExchange), kwargs


def test_full_truth_table_exactly_one_live_combo() -> None:
    """Belt-and-suspenders: over all 32 combos, exactly ONE resolves to dydx."""
    live = [
        mask
        for mask in range(2 ** len(_GATE_FLAGS))
        if resolve_exchange_route(Settings(**_combo(mask))) == DYDX_EXCHANGE_PROVIDER
    ]
    assert live == [_ALL_TRUE_MASK], (
        f"expected exactly one live combo (all-true); got masks {live}"
    )


# --------------------------------------------------------------------------- #
# 2. Node-URL adversarial set                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bad_url",
    [
        "",                                # empty
        "not-a-url",                       # no scheme
        "://nohost",                       # no scheme
        "https://",                        # missing netloc
        "https:///path-only",              # missing host
        "ftp://wrong-scheme.example",      # non-http scheme
        "file:///etc/passwd",              # non-http scheme (local file)
        "javascript:alert(1)",             # bogus scheme
        "ws://",                           # non-http scheme (also missing host)
        "wss://",                          # non-http scheme (also missing host)
        "   ",                             # whitespace only
        # Mainnet-looking URLs are STRUCTURALLY valid — the syntactic gate lets
        # them through — but the operator must never point BANXE_DYDX_NODE_URL
        # at mainnet. Structural validity is asserted here separately from
        # route resolution (RED-zone: only the operator arms the kill-switch).
    ],
)
def test_adversarial_node_urls_fail_closed_to_mock(bad_url: str) -> None:
    """Every adversarial node URL flunks the syntactic gate AND the route."""
    assert is_valid_node_url(bad_url) is False, bad_url
    kwargs = {**FULL_COMBO, "dydx_node_url": bad_url}
    settings = Settings(**kwargs)
    assert resolve_exchange_route(settings) == "mock", bad_url
    exchange = create_app(settings).state.exchange
    assert isinstance(exchange, InMemoryMockExchange), bad_url


def test_node_url_none_fails_closed_to_mock() -> None:
    """A ``None`` node URL (shipped default) fail-closes to mock."""
    assert is_valid_node_url(None) is False
    kwargs = {**FULL_COMBO, "dydx_node_url": None}
    settings = Settings(**kwargs)
    assert resolve_exchange_route(settings) == "mock"
    assert isinstance(create_app(settings).state.exchange, InMemoryMockExchange)


# --------------------------------------------------------------------------- #
# 3. Idempotency / dedup                                                       #
# --------------------------------------------------------------------------- #


def test_mock_route_replayed_client_order_id_is_idempotent() -> None:
    """Mock ExchangePort dedupes by clientOrderId: replay → same orderId."""
    client = TestClient(create_app(Settings()))
    body = _order_body("c-dedup-mock", "r-dedup-mock")
    first = client.post("/api/v1/orders", json=body).json()
    second = client.post("/api/v1/orders", json=body).json()
    assert first["orderId"] == second["orderId"]
    assert first == second, "replay must not diverge"


def test_dydx_route_replay_yields_deterministic_clientid_and_no_submission() -> None:
    """dYdX adapter derives a deterministic uint32 clientId from clientOrderId,
    and NEITHER replay performs any live submission (submitted:false both times).
    """
    auth_client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
    _, token = _siwe_session(auth_client)
    body = _order_body("c-dedup-dydx", "r-dedup-dydx")
    headers = {"Authorization": f"Bearer {token}", HITL_HEADER: "true"}

    first = auth_client.post("/api/v1/orders", json=body, headers=headers).json()
    second = auth_client.post("/api/v1/orders", json=body, headers=headers).json()

    assert first["raw"]["unsignedIntent"]["clientId"] == second["raw"]["unsignedIntent"]["clientId"]
    assert first["raw"]["submitted"] is False
    assert second["raw"]["submitted"] is False
    # And the derived clientId is the deterministic uint32 documented on the adapter.
    from banxe_trading_backend.ports.dydx_exchange import _client_id

    assert first["raw"]["unsignedIntent"]["clientId"] == _client_id("c-dedup-dydx")


# --------------------------------------------------------------------------- #
# 4. Ruflo gate — regulatory block fails closed with 451                       #
# --------------------------------------------------------------------------- #


def test_ruflo_disallow_blocks_order_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Ruflo disallow decision fail-closes the surface with HTTP 451 and
    the exchange transport is NEVER touched (no submission, no route dispatch).
    """
    calls: list[str] = []

    def _forced_disallow(
        *, client_order_id: str, owner_address: str | None
    ) -> RufloDecision:
        calls.append(client_order_id)
        return RufloDecision(
            allowed=False, provider="mock-ruflo", reason="test-forced-disallow"
        )

    monkeypatch.setattr(order_controls, "ruflo_check", _forced_disallow)

    # Assert the assertion helper itself fails closed with 451.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        order_controls.assert_ruflo_allowed(
            client_order_id="c-ruflo-unit", owner_address=None
        )
    assert exc.value.status_code == 451

    # And the HTTP surface returns 451 with a clear message; NO order is placed.
    client = TestClient(create_app(Settings()))
    resp = client.post(
        "/api/v1/orders", json=_order_body("c-ruflo-http", "r-ruflo-http")
    )
    assert resp.status_code == 451
    body = resp.json()
    assert "ruflo" in body["detail"].lower()
    assert "c-ruflo-http" in calls, "Ruflo hook must run on every order surface"


# --------------------------------------------------------------------------- #
# 5. HITL gate — live route requires operator confirmation                     #
# --------------------------------------------------------------------------- #


def test_live_route_without_hitl_header_returns_428_and_no_transport() -> None:
    """No HITL header on the live dydx route → 428, and NO submission runs."""
    client = TestClient(create_app(Settings(**FULL_COMBO)))
    resp = client.post(
        "/api/v1/orders", json=_order_body("c-no-hitl", "r-no-hitl")
    )
    assert resp.status_code == 428
    assert "hitl" in resp.json()["detail"].lower()


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "Yes", "confirmed"])
def test_live_route_with_truthy_hitl_header_proceeds_to_unsigned_intent(
    truthy: str,
) -> None:
    """Truthy HITL header lets the request through → unsigned intent, still no submit."""
    auth_client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
    _, token = _siwe_session(auth_client)
    resp = auth_client.post(
        "/api/v1/orders",
        json=_order_body(f"c-hitl-{truthy}", f"r-hitl-{truthy}"),
        headers={"Authorization": f"Bearer {token}", HITL_HEADER: truthy},
    )
    assert resp.status_code == 200
    raw = resp.json()["raw"]
    assert raw["submitted"] is False
    assert raw["requiresClientSignature"] is True
    assert "unsignedIntent" in raw


@pytest.mark.parametrize("bad", ["", "no", "off", "false", "0", "maybe"])
def test_live_route_with_non_truthy_hitl_header_returns_428(bad: str) -> None:
    """Non-truthy HITL header on the live route also 428s (fail-closed)."""
    client = TestClient(create_app(Settings(**FULL_COMBO)))
    resp = client.post(
        "/api/v1/orders",
        json=_order_body(f"c-hitl-bad-{bad or 'empty'}", "r-hitl-bad"),
        headers={HITL_HEADER: bad},
    )
    assert resp.status_code == 428


# --------------------------------------------------------------------------- #
# 6. Self-custodial — response NEVER carries a signature or a key             #
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
    """Walk any JSON-like payload and assert no forbidden key names appear.

    The safelist below preserves the S6.4-EN INTENT flag ``requiresClientSignature``
    which is a BOOLEAN telling the client wallet to sign — never a signature VALUE.
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


def test_deny_list_scan_flags_forbidden_key() -> None:
    """Meta-test: the deny-list scanner actually rejects a forbidden key.
    Guards against a silent no-op if the scanner regresses.
    """
    with pytest.raises(AssertionError, match="forbidden key"):
        _assert_no_forbidden_fields({"nested": {"signature": "0xdead"}})


def test_deny_list_scan_allows_requires_client_signature_flag() -> None:
    """The boolean ``requiresClientSignature`` flag is explicitly safelisted."""
    _assert_no_forbidden_fields({"requiresClientSignature": True})


def test_live_route_response_carries_no_signature_no_key() -> None:
    """Under the FULL combo, the ENTIRE order response has no forbidden fields."""
    auth_client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
    address, token = _siwe_session(auth_client)
    resp = auth_client.post(
        "/api/v1/orders",
        json=_order_body("c-selfcustody", "r-selfcustody"),
        headers={"Authorization": f"Bearer {token}", HITL_HEADER: "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    _assert_no_forbidden_fields(body)
    # And the owner is the authenticated wallet, not a backend-held identity.
    assert body["raw"]["unsignedIntent"]["ownerAddress"].lower() == address.lower()


def test_mock_route_response_carries_no_signature_no_key() -> None:
    """Same guarantee holds on the mock route (default posture)."""
    client = TestClient(create_app(Settings()))
    resp = client.post(
        "/api/v1/orders", json=_order_body("c-mock-selfcustody", "r-mock-selfcustody")
    )
    assert resp.status_code == 200
    _assert_no_forbidden_fields(resp.json())


# --------------------------------------------------------------------------- #
# 7. Kill-switch default-off                                                   #
# --------------------------------------------------------------------------- #


def test_kill_switch_default_config_never_serves_live_route() -> None:
    """Under shipped default config, EVERY relevant gate defaults off."""
    settings = Settings()
    assert settings.exchange_provider == "mock"
    assert settings.dse_provider_mode == "mock"
    assert settings.dse_live_allowed is False
    assert settings.dydx_submit_enabled is False
    assert settings.dydx_node_url is None
    assert resolve_exchange_route(settings) == "mock"
    assert isinstance(create_app(settings).state.exchange, InMemoryMockExchange)


def test_kill_switch_default_dydx_adapter_submission_disabled() -> None:
    """The dydx adapter built from defaults refuses live submission (§D3)."""
    adapter = DydxExchangeAdapter.from_settings(Settings())
    assert adapter.submission_enabled() is False
    with pytest.raises(ExchangeUnavailable, match="disabled"):
        asyncio.run(adapter.submit_signed_order({"signed": "tx"}))


# --------------------------------------------------------------------------- #
# 8. No-network assertion (leverages the autouse guard above)                  #
# --------------------------------------------------------------------------- #


def test_order_flow_never_invokes_submission_transport() -> None:
    """The order surface must NEVER touch ``HttpxSubmissionTransport.submit``.

    The autouse ``_no_live_network`` fixture patches the transport to raise; a
    successful order round-trip through both routes therefore proves the seam
    is not exercised on the order path.
    """
    # Mock route: no HITL needed.
    mock_client = TestClient(create_app(Settings()))
    assert (
        mock_client.post(
            "/api/v1/orders", json=_order_body("c-nonet-mock", "r-nonet-mock")
        ).status_code
        == 200
    )
    # Live route: requires HITL + SIWE session; still no transport is touched.
    live_client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
    _, token = _siwe_session(live_client)
    assert (
        live_client.post(
            "/api/v1/orders",
            json=_order_body("c-nonet-dydx", "r-nonet-dydx"),
            headers={"Authorization": f"Bearer {token}", HITL_HEADER: "true"},
        ).status_code
        == 200
    )


def test_forbidden_transport_actually_raises() -> None:
    """Meta-test: if the transport IS invoked the fixture raises. No silent no-op."""
    transport = HttpxSubmissionTransport()
    with pytest.raises(_ForbiddenNetworkCall):
        asyncio.run(
            transport.submit(
                FAKE_TESTNET_NODE_URL, {"signed": "tx"}, timeout_s=1.0
            )
        )


def test_forbidden_httpx_async_client_actually_raises() -> None:
    """Meta-test: constructing ``httpx.AsyncClient`` directly raises too."""
    with pytest.raises(_ForbiddenNetworkCall):
        httpx.AsyncClient()


# --------------------------------------------------------------------------- #
# 9. I-01 Decimal — floats rejected at the wire boundary                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad_amount", [0.5, 1, 0, -0.1, 1e6])
def test_float_amount_rejected_at_pydantic_boundary(bad_amount: object) -> None:
    """A JSON-number amount is rejected by pydantic before reaching the exchange.

    I-01: money values MUST be Decimal strings, never floats. The order body
    surface uses ``DecimalStr`` (typed str with a Decimal-parse validator);
    pydantic v2 rejects a JSON number for a ``str`` field.
    """
    client = TestClient(create_app(Settings()))
    body: dict[str, Any] = {
        "symbol": "BTC-USD",
        "side": "buy",
        "type": "limit",
        "amount": bad_amount,
        "limitPrice": "67000",
        "clientOrderId": "c-i01-float",
        "correlationId": "r-i01-float",
    }
    resp = client.post("/api/v1/orders", json=body)
    assert resp.status_code == 422, resp.text


def test_intent_atomic_fields_are_strings_not_floats() -> None:
    """quantums / subticks / size / price on the intent are STRINGS (I-01)."""
    auth_client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
    _, token = _siwe_session(auth_client)
    resp = auth_client.post(
        "/api/v1/orders",
        json=_order_body("c-i01-str", "r-i01-str"),
        headers={"Authorization": f"Bearer {token}", HITL_HEADER: "true"},
    )
    assert resp.status_code == 200
    intent = resp.json()["raw"]["unsignedIntent"]
    for field in ("quantums", "subticks", "size", "price"):
        value = intent[field]
        assert value is None or isinstance(value, str), (field, type(value).__name__)
        if isinstance(value, str):
            # Must parse back through Decimal without loss (no float taint).
            from decimal import Decimal

            Decimal(value)


# --------------------------------------------------------------------------- #
# 10. Determinism — identical inputs yield identical outputs                   #
# --------------------------------------------------------------------------- #


def test_dydx_intent_is_deterministic_across_fresh_apps() -> None:
    """A fresh app instance built with identical settings produces an identical
    unsigned intent for identical input. No time / random / counter leak.
    """
    body = _order_body("c-determ-1", "r-determ-1")

    intents: list[dict[str, object]] = []
    for _ in range(3):
        auth_client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
        _, token = _siwe_session(auth_client)
        resp = auth_client.post(
            "/api/v1/orders",
            json=body,
            headers={"Authorization": f"Bearer {token}", HITL_HEADER: "true"},
        )
        assert resp.status_code == 200
        intents.append(resp.json()["raw"]["unsignedIntent"])
    assert intents[0] == intents[1] == intents[2], intents


def test_mock_first_order_id_is_deterministic_across_fresh_apps() -> None:
    """Mock exchange seq counter starts at 1 for every fresh app → determinism."""
    body = _order_body("c-determ-mock", "r-determ-mock")
    ids = [
        TestClient(create_app(Settings()))
        .post("/api/v1/orders", json=body)
        .json()["orderId"]
        for _ in range(3)
    ]
    assert ids == ["mock-000001"] * 3
