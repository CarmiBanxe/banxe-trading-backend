"""WalletAuthPort / SIWE adapter — self-custodial wallet auth (ADR-083 D4).

Uses a deterministic TEST keypair (NOT a real key). No network, no custody:
the backend only verifies signatures and mints opaque sessions.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from banxe_trading_backend.ports import SiweAuthAdapter, WalletAuthError, WalletAuthPort

# Deterministic TEST keypair — NOT a real private key.
TEST_KEY = "0x" + "11" * 32
TEST_ADDRESS = Account.from_key(TEST_KEY).address  # 0x19E7E3...aff2A


def build_siwe(
    address: str,
    nonce: str,
    *,
    domain: str = "localhost",
    expiration_time: str | None = None,
) -> str:
    lines = [
        f"{domain} wants you to sign in with your Ethereum account:",
        address,
        "",
        "Sign in to Banxe.",
        "",
        "URI: https://localhost",
        "Version: 1",
        "Chain ID: 1",
        f"Nonce: {nonce}",
        "Issued At: 2026-06-12T00:00:00Z",
    ]
    if expiration_time is not None:
        lines.append(f"Expiration Time: {expiration_time}")
    return "\n".join(lines)


def sign(message: str, key: str = TEST_KEY) -> str:
    signed = Account.sign_message(encode_defunct(text=message), private_key=key)
    return "0x" + signed.signature.hex().removeprefix("0x")


# --------------------------- API (TestClient) ------------------------------- #


def test_nonce_endpoint_issues_nonce(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/nonce")
    assert resp.status_code == 200
    body = resp.json()
    assert body["nonce"]
    assert "issuedAt" in body and "expiresAt" in body


def test_valid_siwe_signature_verifies_and_returns_session(client: TestClient) -> None:
    nonce = client.get("/api/v1/auth/nonce").json()["nonce"]
    message = build_siwe(TEST_ADDRESS, nonce)
    resp = client.post(
        "/api/v1/auth/verify", json={"message": message, "signature": sign(message)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["address"].lower() == TEST_ADDRESS.lower()
    assert body["token"]
    assert "expiresAt" in body


def test_tampered_message_is_rejected(client: TestClient) -> None:
    nonce = client.get("/api/v1/auth/nonce").json()["nonce"]
    message = build_siwe(TEST_ADDRESS, nonce)
    signature = sign(message)
    # Claim a different address than the signer → recovery mismatch → 401.
    forged = build_siwe("0x000000000000000000000000000000000000dEaD", nonce)
    resp = client.post("/api/v1/auth/verify", json={"message": forged, "signature": signature})
    assert resp.status_code == 401


def test_replayed_nonce_is_rejected(client: TestClient) -> None:
    nonce = client.get("/api/v1/auth/nonce").json()["nonce"]
    message = build_siwe(TEST_ADDRESS, nonce)
    signature = sign(message)
    first = client.post("/api/v1/auth/verify", json={"message": message, "signature": signature})
    assert first.status_code == 200
    replay = client.post("/api/v1/auth/verify", json={"message": message, "signature": signature})
    assert replay.status_code == 401  # single-use nonce consumed


def test_unknown_nonce_is_rejected(client: TestClient) -> None:
    message = build_siwe(TEST_ADDRESS, "never-issued-nonce")
    resp = client.post(
        "/api/v1/auth/verify", json={"message": message, "signature": sign(message)}
    )
    assert resp.status_code == 401


# --------------------------- adapter unit tests ----------------------------- #


def test_adapter_satisfies_walletauthport_protocol() -> None:
    assert isinstance(SiweAuthAdapter(signing_key="k", domain="localhost"), WalletAuthPort)


def test_expired_nonce_is_rejected() -> None:
    clock = {"t": 1000.0}
    adapter = SiweAuthAdapter(
        signing_key="k", domain="localhost", nonce_ttl_seconds=300, now=lambda: clock["t"]
    )
    challenge = adapter.issue_nonce()
    message = build_siwe(TEST_ADDRESS, challenge.nonce)
    signature = sign(message)
    clock["t"] = 1000.0 + 301  # past the nonce TTL
    with pytest.raises(WalletAuthError):
        adapter.verify(message, signature)


def test_domain_mismatch_is_rejected() -> None:
    adapter = SiweAuthAdapter(signing_key="k", domain="banxe.app")
    challenge = adapter.issue_nonce()
    message = build_siwe(TEST_ADDRESS, challenge.nonce, domain="evil.example")
    with pytest.raises(WalletAuthError, match="domain"):
        adapter.verify(message, sign(message))


def test_expired_siwe_message_is_rejected() -> None:
    t0 = datetime(2026, 6, 12, 0, 0, 0, tzinfo=UTC).timestamp()
    clock = {"t": t0}
    adapter = SiweAuthAdapter(
        signing_key="k", domain="localhost", nonce_ttl_seconds=300, now=lambda: clock["t"]
    )
    challenge = adapter.issue_nonce()
    exp_iso = datetime.fromtimestamp(t0 + 10, tz=UTC).isoformat()
    message = build_siwe(TEST_ADDRESS, challenge.nonce, expiration_time=exp_iso)
    signature = sign(message)
    clock["t"] = t0 + 60  # nonce still valid (<300s) but SIWE Expiration passed
    with pytest.raises(WalletAuthError, match="expired"):
        adapter.verify(message, signature)


def test_session_token_roundtrip_and_tamper() -> None:
    adapter = SiweAuthAdapter(signing_key="k", domain="localhost")
    challenge = adapter.issue_nonce()
    message = build_siwe(TEST_ADDRESS, challenge.nonce)
    session = adapter.verify(message, sign(message))
    validated = adapter.validate_token(session.token)
    assert validated is not None
    assert validated.address.lower() == TEST_ADDRESS.lower()
    assert adapter.validate_token(session.token + "tamper") is None
