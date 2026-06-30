"""S6.4-EN Phase-2a conformance — dydx ExchangePort route gate + RED-zone controls.

Asserts the §E acceptance criteria of the authorising spec:

  1. Selection matrix — the dYdX adapter is selected ONLY under the FULL combo
     (provider=dydx + sandbox-live mode + master kill-switch + per-venue
     kill-switch + valid testnet node URL); any other combination fail-closes
     to the in-memory mock.
  2. Fail-closed — kill-switch off / missing node URL → no submit, mock fallback.
  3. Unsigned intent — under the live route the backend STILL produces only an
     unsigned intent (``submitted:false``); the response carries NO signature
     and NO key (ADR-083 self-custodial).
  4. Ruflo + HITL — order surface routes through the regulatory check; HITL
     gate fail-closes a live placement without the operator confirmation header.
  5. Idempotency — duplicate ``clientOrderId`` returns the same outcome.
  6. I-01 — order qty/price/quantums are decimal strings (no float).

NO live network, NO real keys, NO real endpoints in CI — only obviously-fake
placeholders confined to this file.
"""

from __future__ import annotations

from typing import Any

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
    InMemoryMockExchange,
)
from banxe_trading_backend.services.order_controls import (
    HITL_HEADER,
    assert_hitl_confirmed,
    assert_ruflo_allowed,
    ruflo_check,
)

# Obviously-fake placeholders — NOT a real testnet endpoint. Tests only.
FAKE_TESTNET_NODE_URL = "https://example-dydx-testnet-node.invalid"

# FULL S6.4-EN combo — every flag/URL required to select the dydx route.
FULL_COMBO: dict[str, Any] = {
    "exchange_provider": "dydx",
    "dse_provider_mode": "sandbox-live",
    "dse_live_allowed": True,
    "dydx_submit_enabled": True,
    "dydx_node_url": FAKE_TESTNET_NODE_URL,
}


def _build_exchange_for(**overrides: Any) -> object:
    """Resolve the ExchangePort the app would build under ``overrides``."""
    return create_app(Settings(**overrides)).state.exchange


def _build_route_for(**overrides: Any) -> str:
    return create_app(Settings(**overrides)).state.exchange_route


# --------------------------------------------------------------------------- #
# 1. Selection matrix                                                          #
# --------------------------------------------------------------------------- #


def test_selection_full_combo_routes_to_dydx() -> None:
    """All five gating conditions ON → dYdX adapter selected."""
    exchange = _build_exchange_for(**FULL_COMBO)
    assert isinstance(exchange, DydxExchangeAdapter)
    assert _build_route_for(**FULL_COMBO) == DYDX_EXCHANGE_PROVIDER


def test_selection_defaults_route_to_mock() -> None:
    """Shipped default config → deterministic in-memory mock (CI-safe)."""
    exchange = _build_exchange_for()
    assert isinstance(exchange, InMemoryMockExchange)
    assert _build_route_for() == "mock"


@pytest.mark.parametrize(
    "drop",
    [
        "exchange_provider",  # provider=mock → mock
        "dse_provider_mode",  # mode=mock → mock
        "dse_live_allowed",  # master kill-switch off → mock
        "dydx_submit_enabled",  # per-venue kill-switch off → mock
        "dydx_node_url",  # node URL missing → mock
    ],
)
def test_selection_drop_any_flag_fails_closed_to_mock(drop: str) -> None:
    """Dropping ANY of the five gating conditions → fail-closed to mock."""
    partial = {k: v for k, v in FULL_COMBO.items() if k != drop}
    exchange = _build_exchange_for(**partial)
    assert isinstance(exchange, InMemoryMockExchange)
    assert _build_route_for(**partial) == "mock"


@pytest.mark.parametrize(
    "bad_url",
    ["", "not-a-url", "://no-scheme", "ftp://wrong-scheme.example", "https://"],
)
def test_selection_invalid_node_url_fails_closed_to_mock(bad_url: str) -> None:
    """A syntactically invalid node URL → fail-closed to mock (never live)."""
    config = {**FULL_COMBO, "dydx_node_url": bad_url}
    exchange = _build_exchange_for(**config)
    assert isinstance(exchange, InMemoryMockExchange)
    assert _build_route_for(**config) == "mock"


def test_resolver_helper_returns_dydx_only_under_full_combo() -> None:
    """Direct unit test of the resolver: dydx iff all five gating conditions ON."""
    assert resolve_exchange_route(Settings(**FULL_COMBO)) == DYDX_EXCHANGE_PROVIDER
    for drop in FULL_COMBO:
        partial = {k: v for k, v in FULL_COMBO.items() if k != drop}
        assert resolve_exchange_route(Settings(**partial)) == "mock", drop
    assert resolve_exchange_route(Settings()) == "mock"


def test_kill_switch_default_is_off() -> None:
    """The per-venue kill-switch ships OFF by default; the master kill-switch too."""
    settings = Settings()
    assert settings.dydx_submit_enabled is False
    assert settings.dse_live_allowed is False
    assert settings.dydx_node_url is None
    assert settings.exchange_provider == "mock"


# --------------------------------------------------------------------------- #
# 3. Unsigned-intent — self-custodial (ADR-083)                                #
# --------------------------------------------------------------------------- #


def _siwe_session(client: TestClient, key: str) -> tuple[str, str]:
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


def test_live_route_still_returns_unsigned_intent_no_signature_no_key() -> None:
    """Under the FULL combo the response carries an UNSIGNED intent + NO key/sig."""
    client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
    key = "0x" + "11" * 32
    address, token = _siwe_session(client, key)

    resp = client.post(
        "/api/v1/orders",
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "type": "limit",
            "amount": "0.5",
            "limitPrice": "67000",
            "clientOrderId": "c-unsigned-1",
            "correlationId": "r-unsigned-1",
        },
        headers={"Authorization": f"Bearer {token}", HITL_HEADER: "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    raw = body["raw"]
    assert raw["submitted"] is False  # NO live submission performed
    assert raw["requiresClientSignature"] is True

    intent = raw["unsignedIntent"]
    # Self-custodial: the backend produces NO signature and HOLDS NO key. The
    # only signature-related field is the BOOLEAN ``requiresClientSignature``
    # flag (telling the client to sign) — never a signature value or a key.
    for forbidden_key in (
        "signature", "signedTx", "signedTransaction", "privateKey", "secret",
    ):
        assert forbidden_key not in intent, forbidden_key
        assert forbidden_key not in raw, forbidden_key
    # Owner is the authenticated wallet address — the backend NEVER holds keys.
    assert intent["ownerAddress"].lower() == address.lower()
    assert intent["requiresClientSignature"] is True


# --------------------------------------------------------------------------- #
# 4. Ruflo + HITL controls                                                     #
# --------------------------------------------------------------------------- #


def test_ruflo_mock_allows_by_default() -> None:
    """Default Ruflo posture is a deterministic mock allow (BUG-005 hook PRESENT)."""
    decision = ruflo_check(client_order_id="c1", owner_address="0xabc")
    assert decision.allowed is True
    assert decision.provider == "mock-ruflo"
    # assert_* helper does not raise on the allow path
    assert_ruflo_allowed(client_order_id="c1", owner_address="0xabc")


def test_hitl_assertion_passes_with_truthy_header() -> None:
    """A canonical truthy HITL header value satisfies the assertion."""
    for truthy in ("1", "true", "TRUE", "Yes", "confirmed"):
        assert_hitl_confirmed(header_value=truthy)


def test_hitl_assertion_fails_closed_without_confirm() -> None:
    """Missing or non-truthy HITL header → HTTPException 428 (Precondition Required)."""
    from fastapi import HTTPException

    for missing in (None, "", "no", "off", "false"):
        with pytest.raises(HTTPException) as exc:
            assert_hitl_confirmed(header_value=missing)
        assert exc.value.status_code == 428


def test_live_route_order_without_hitl_header_fails_closed_428() -> None:
    """Live route + no HITL header → 428 (no submit, no order created)."""
    client = TestClient(create_app(Settings(**FULL_COMBO)))
    resp = client.post(
        "/api/v1/orders",
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "type": "limit",
            "amount": "0.5",
            "limitPrice": "67000",
            "clientOrderId": "c-no-hitl",
            "correlationId": "r-no-hitl",
        },
    )
    assert resp.status_code == 428
    assert "hitl" in resp.json()["detail"].lower()


def test_mock_route_order_does_not_require_hitl_header() -> None:
    """Mock route does NOT require HITL — only the live dydx route triggers it."""
    client = TestClient(create_app(Settings()))
    resp = client.post(
        "/api/v1/orders",
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "type": "limit",
            "amount": "0.5",
            "limitPrice": "67000",
            "clientOrderId": "c-mock-no-hitl",
            "correlationId": "r-mock-no-hitl",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["raw"]["mock"] is True


# --------------------------------------------------------------------------- #
# 5. Idempotency on clientOrderId                                              #
# --------------------------------------------------------------------------- #


def test_mock_route_idempotency_returns_same_order_id() -> None:
    """Mock ExchangePort idempotency: replay of the same clientOrderId → same id."""
    client = TestClient(create_app(Settings()))
    body = {
        "symbol": "BTC-USD",
        "side": "buy",
        "type": "limit",
        "amount": "0.5",
        "limitPrice": "67000",
        "clientOrderId": "c-idem-1",
        "correlationId": "r-idem-1",
    }
    first = client.post("/api/v1/orders", json=body).json()
    second = client.post("/api/v1/orders", json=body).json()
    assert first["orderId"] == second["orderId"]


def test_dydx_route_deterministic_client_id_is_idempotent() -> None:
    """dYdX adapter derives a deterministic uint32 clientId from clientOrderId."""
    headers = {HITL_HEADER: "true"}
    client = TestClient(create_app(Settings(**FULL_COMBO)))
    # owner_address required for the dydx adapter — set via SIWE session.
    auth_client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
    key = "0x" + "11" * 32
    _, token = _siwe_session(auth_client, key)
    body = {
        "symbol": "BTC-USD",
        "side": "buy",
        "type": "limit",
        "amount": "0.5",
        "limitPrice": "67000",
        "clientOrderId": "c-idem-dydx-1",
        "correlationId": "r-idem-dydx-1",
    }
    first = auth_client.post(
        "/api/v1/orders",
        json=body,
        headers={"Authorization": f"Bearer {token}", **headers},
    ).json()
    second = auth_client.post(
        "/api/v1/orders",
        json=body,
        headers={"Authorization": f"Bearer {token}", **headers},
    ).json()
    # Same clientOrderId → same deterministic dydx clientId on the intent.
    assert first["raw"]["unsignedIntent"]["clientId"] == second["raw"]["unsignedIntent"]["clientId"]
    assert first["orderId"] == second["orderId"]
    # And no submission performed in either replay.
    assert first["raw"]["submitted"] is False
    assert second["raw"]["submitted"] is False
    # touch unused symbol so ruff does not flag the import
    assert client is not None


# --------------------------------------------------------------------------- #
# 6. I-01 decimal strings (no float)                                           #
# --------------------------------------------------------------------------- #


def test_intent_quantums_subticks_size_are_decimal_strings() -> None:
    """quantums/subticks/size are atomic-integer/decimal STRINGS (I-01)."""
    auth_client = TestClient(create_app(Settings(auth_enabled=True, **FULL_COMBO)))
    key = "0x" + "11" * 32
    _, token = _siwe_session(auth_client, key)
    resp = auth_client.post(
        "/api/v1/orders",
        json={
            "symbol": "BTC-USD",
            "side": "buy",
            "type": "limit",
            "amount": "0.5",
            "limitPrice": "67000",
            "clientOrderId": "c-i01",
            "correlationId": "r-i01",
        },
        headers={"Authorization": f"Bearer {token}", HITL_HEADER: "true"},
    )
    assert resp.status_code == 200
    intent = resp.json()["raw"]["unsignedIntent"]
    for field in ("quantums", "subticks", "size", "price"):
        value = intent[field]
        assert value is None or isinstance(value, str), (field, type(value))
    # Numeric value sanity: not produced from float arithmetic.
    assert intent["quantums"] == "5000000000"
    assert intent["subticks"] == "6700000000"


# --------------------------------------------------------------------------- #
# 2. Fail-closed semantics — never silent live, never hard-fail                #
# --------------------------------------------------------------------------- #


def test_partial_combo_does_not_select_dydx_adapter() -> None:
    """Partial config is silently routed to mock at build time (never raise)."""
    # Only the per-venue kill-switch + URL set; missing the master kill-switch
    # and the sandbox-live mode → fail-closed to mock.
    exchange = _build_exchange_for(
        exchange_provider="dydx",
        dydx_submit_enabled=True,
        dydx_node_url=FAKE_TESTNET_NODE_URL,
    )
    assert isinstance(exchange, InMemoryMockExchange)


def test_dydx_submit_disabled_keeps_adapter_submission_gate_closed() -> None:
    """Even if the adapter is instantiated, its submission gate stays closed
    unless BOTH the per-venue kill-switch AND a valid node URL are set."""
    adapter = DydxExchangeAdapter.from_settings(Settings())
    assert adapter.submission_enabled() is False
