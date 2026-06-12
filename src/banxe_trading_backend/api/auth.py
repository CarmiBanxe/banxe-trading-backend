"""Wallet auth REST router (ADR-083 D4) — SIWE nonce + verify.

GET  /auth/nonce  → a server nonce the wallet must include in the SIWE message.
POST /auth/verify → verify the signed SIWE message; return an opaque session.

Self-custodial: the backend verifies signatures and mints sessions only. It
holds NO private keys and takes NO custody. REST only (no GraphQL, no Keycloak).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from banxe_trading_backend.models import NonceResponse, SessionResponse, VerifyRequest
from banxe_trading_backend.ports import WalletAuthError, WalletAuthPort
from banxe_trading_backend.ports.wallet_auth_port import _iso

from .deps import get_wallet_auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/nonce", response_model=NonceResponse)
async def get_nonce(auth: WalletAuthPort = Depends(get_wallet_auth)) -> NonceResponse:
    challenge = auth.issue_nonce()
    return NonceResponse(
        nonce=challenge.nonce,
        issued_at=_iso(challenge.issued_at),
        expires_at=_iso(challenge.expires_at),
    )


@router.post("/verify", response_model=SessionResponse)
async def verify(
    body: VerifyRequest,
    auth: WalletAuthPort = Depends(get_wallet_auth),
) -> SessionResponse:
    try:
        session = auth.verify(body.message, body.signature)
    except WalletAuthError as exc:
        # 401: any SIWE failure (bad signature / domain / nonce / expiry).
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return SessionResponse(
        address=session.address,
        token=session.token,
        expires_at=_iso(session.expires_at),
    )
