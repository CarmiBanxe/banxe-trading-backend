"""FastAPI dependencies: typed access to the ports stored on app.state.

TODO(ADR-021 / ADR-017): an ``AuthPort`` dependency (backend-issued opaque
session token; NOT Keycloak) gates order endpoints once auth is enabled. The
seam is documented here; the mechanism is governance-gated.
"""

from __future__ import annotations

from fastapi import Request

from banxe_trading_backend.ports import ExchangePort, MarketDataPort


def get_exchange(request: Request) -> ExchangePort:
    """Return the configured ExchangePort adapter (mock in the skeleton)."""
    exchange: ExchangePort = request.app.state.exchange
    return exchange


def get_market_data(request: Request) -> MarketDataPort:
    """Return the configured MarketDataPort adapter (mock in the skeleton)."""
    market_data: MarketDataPort = request.app.state.market_data
    return market_data
