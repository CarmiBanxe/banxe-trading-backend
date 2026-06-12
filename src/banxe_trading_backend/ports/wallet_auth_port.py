"""WalletAuthPort — self-custodial wallet authentication (ADR-083 D4, S6.4).

Replaces the Keycloak-free AuthPort TODO with **Sign-In-with-Ethereum (SIWE,
EIP-4361)**. The frontend connects a wallet and signs a SIWE challenge; this
backend **verifies the signature recovers the claimed address** and issues an
**opaque session token**. The backend holds **NO private keys** and takes **NO
custody** — it only verifies signatures (public-key crypto) and mints sessions.

Signature recovery uses `eth-account` (MIT). No third-party API keys / secrets
are involved in SIWE verification — it is signature-based.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from eth_account import Account
from eth_account.messages import encode_defunct

if TYPE_CHECKING:
    from banxe_trading_backend.config import Settings


class WalletAuthError(Exception):
    """SIWE verification failed (bad signature / domain / nonce / expiry)."""


@dataclass(frozen=True)
class NonceChallenge:
    nonce: str
    issued_at: float
    expires_at: float


@dataclass(frozen=True)
class Session:
    address: str
    token: str
    expires_at: float


@dataclass(frozen=True)
class SiweFields:
    domain: str
    address: str
    nonce: str
    expiration_time: float | None


@runtime_checkable
class WalletAuthPort(Protocol):
    """Issue SIWE nonces and verify signed SIWE messages → opaque session."""

    def issue_nonce(self) -> NonceChallenge: ...

    def verify(self, message: str, signature: str) -> Session: ...


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def parse_siwe_message(message: str) -> SiweFields:
    """Minimal EIP-4361 parser — extracts the fields we authenticate on."""
    lines = message.splitlines()
    if len(lines) < 2 or " wants you to sign in" not in lines[0]:
        raise WalletAuthError("malformed SIWE message")
    domain = lines[0].split(" wants you to sign in", 1)[0].strip()
    address = lines[1].strip()
    fields: dict[str, str] = {}
    for line in lines[2:]:
        if ": " in line:
            key, _, value = line.partition(": ")
            fields[key.strip()] = value.strip()
    nonce = fields.get("Nonce")
    if not domain or not address or not nonce:
        raise WalletAuthError("SIWE message missing domain/address/nonce")
    expiration: float | None = None
    raw_exp = fields.get("Expiration Time")
    if raw_exp:
        try:
            expiration = datetime.fromisoformat(raw_exp.replace("Z", "+00:00")).timestamp()
        except ValueError as exc:
            raise WalletAuthError("invalid SIWE Expiration Time") from exc
    return SiweFields(domain=domain, address=address, nonce=nonce, expiration_time=expiration)


class _SessionTokenService:
    """Mints/validates HMAC-signed opaque session tokens (no JWT, no custody)."""

    def __init__(self, signing_key: str) -> None:
        self._key = signing_key.encode()

    def mint(self, address: str, expires_at: float) -> str:
        session_id = secrets.token_urlsafe(16)
        payload = f"{address}|{session_id}|{expires_at:.0f}"
        sig = hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()
        raw = f"{payload}|{sig}"
        return base64.urlsafe_b64encode(raw.encode()).decode()

    def validate(self, token: str, *, now: float) -> Session | None:
        try:
            raw = base64.urlsafe_b64decode(token.encode()).decode()
            address, session_id, expires_str, sig = raw.split("|")
        except (ValueError, UnicodeDecodeError):
            return None
        payload = f"{address}|{session_id}|{expires_str}"
        expected = hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        expires_at = float(expires_str)
        if now >= expires_at:
            return None
        return Session(address=address, token=token, expires_at=expires_at)


class SiweAuthAdapter:
    """WalletAuthPort over SIWE/EIP-4361. Self-custodial — no private keys."""

    def __init__(
        self,
        *,
        signing_key: str,
        domain: str,
        nonce_ttl_seconds: int = 300,
        session_ttl_seconds: int = 86_400,
        now: Callable[[], float] = time.time,
        nonce_factory: Callable[[], str] = lambda: secrets.token_urlsafe(16),
    ) -> None:
        self._tokens = _SessionTokenService(signing_key)
        self._domain = domain
        self._nonce_ttl = nonce_ttl_seconds
        self._session_ttl = session_ttl_seconds
        self._now = now
        self._nonce_factory = nonce_factory
        # In-memory single-use nonce store: nonce -> issued_at.
        self._nonces: dict[str, float] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> SiweAuthAdapter:
        return cls(
            signing_key=settings.session_signing_key,
            domain=settings.siwe_domain,
            nonce_ttl_seconds=settings.nonce_ttl_seconds,
            session_ttl_seconds=settings.session_ttl_seconds,
        )

    def issue_nonce(self) -> NonceChallenge:
        now = self._now()
        self._evict_expired(now)
        nonce = self._nonce_factory()
        self._nonces[nonce] = now
        return NonceChallenge(nonce=nonce, issued_at=now, expires_at=now + self._nonce_ttl)

    def verify(self, message: str, signature: str) -> Session:
        fields = parse_siwe_message(message)
        recovered = self._recover(message, signature)
        if recovered.lower() != fields.address.lower():
            raise WalletAuthError("signature does not match the claimed address")
        if fields.domain != self._domain:
            raise WalletAuthError("SIWE domain mismatch")
        self._consume_nonce(fields.nonce)
        now = self._now()
        if fields.expiration_time is not None and now >= fields.expiration_time:
            raise WalletAuthError("SIWE message has expired")
        expires_at = now + self._session_ttl
        token = self._tokens.mint(recovered, expires_at)
        return Session(address=recovered, token=token, expires_at=expires_at)

    def validate_token(self, token: str) -> Session | None:
        return self._tokens.validate(token, now=self._now())

    @staticmethod
    def _recover(message: str, signature: str) -> str:
        try:
            sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        except ValueError as exc:
            raise WalletAuthError("malformed signature") from exc
        try:
            return Account.recover_message(encode_defunct(text=message), signature=sig_bytes)
        except Exception as exc:  # noqa: BLE001 - any recovery failure → auth error (no leak)
            raise WalletAuthError("could not recover signer from signature") from exc

    def _consume_nonce(self, nonce: str) -> None:
        now = self._now()
        issued_at = self._nonces.pop(nonce, None)  # single-use: pop = consume
        if issued_at is None:
            raise WalletAuthError("unknown, expired, or replayed nonce")
        if now - issued_at > self._nonce_ttl:
            raise WalletAuthError("nonce expired")

    def _evict_expired(self, now: float) -> None:
        stale = [n for n, ts in self._nonces.items() if now - ts > self._nonce_ttl]
        for n in stale:
            self._nonces.pop(n, None)
