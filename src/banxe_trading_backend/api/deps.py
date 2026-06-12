"""FastAPI dependencies: typed access to the ports stored on app.state.

Wallet auth (ADR-083 D4) is the SIWE ``WalletAuthPort`` — backend-issued opaque
session token, self-custodial, NOT Keycloak. ``require_session`` gates order
endpoints on a valid session when ``auth_enabled`` is set.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from banxe_trading_backend.ports import ExchangePort, MarketDataPort, WalletAuthPort
from banxe_trading_backend.ports.wallet_auth_port import Session


def get_exchange(request: Request) -> ExchangePort:
    """Return the configured ExchangePort adapter (mock in the skeleton)."""
    exchange: ExchangePort = request.app.state.exchange
    return exchange


def get_market_data(request: Request) -> MarketDataPort:
    """Return the configured MarketDataPort adapter (mock in the skeleton)."""
    market_data: MarketDataPort = request.app.state.market_data
    return market_data


def get_wallet_auth(request: Request) -> WalletAuthPort:
    """Return the configured WalletAuthPort (SIWE; self-custodial, no keys)."""
    wallet_auth: WalletAuthPort = request.app.state.wallet_auth
    return wallet_auth


def require_session(
    request: Request,
    auth: WalletAuthPort = Depends(get_wallet_auth),
) -> Session | None:
    """Require a valid SIWE wallet session when auth is enabled (ADR-083 D4).

    When ``auth_enabled`` is False (default — mock/CI) this is a no-op and returns
    None. When True, a valid ``Authorization: Bearer <token>`` session is required
    (self-custodial; the token is opaque, not a key) — else 401.
    """
    if not request.app.state.settings.auth_enabled:
        return None
    header = request.headers.get("authorization", "")
    if header[:7].lower() != "bearer ":
        raise HTTPException(status_code=401, detail="missing bearer wallet session")
    session = auth.validate_token(header[7:].strip())
    if session is None:
        raise HTTPException(status_code=401, detail="invalid or expired wallet session")
    return session
