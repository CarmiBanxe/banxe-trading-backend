"""FastAPI dependencies: typed access to the ports stored on app.state.

Wallet auth (ADR-083 D4) is the SIWE ``WalletAuthPort`` — backend-issued opaque
session token, self-custodial, NOT Keycloak. Gating order endpoints on a valid
session is a follow-up step (S6.4+).
"""

from __future__ import annotations

from fastapi import Request

from banxe_trading_backend.ports import ExchangePort, MarketDataPort, WalletAuthPort


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
