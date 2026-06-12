"""FastAPI application factory (ADR-021 skeleton).

Wires the REST routers + the order-book WS onto the configured ports. Adapter
selection is provider-parameterized (config); only the in-memory mocks ship in
the skeleton, so the whole surface runs deterministically with no live exchange
or market-data provider.
"""

from __future__ import annotations

from fastapi import FastAPI

from banxe_trading_backend import __version__
from banxe_trading_backend.api import orders_router, rate_router, symbols_router
from banxe_trading_backend.config import Settings, get_settings
from banxe_trading_backend.ports import (
    ExchangePort,
    InMemoryMockExchange,
    InMemoryMockMarketData,
    MarketDataPort,
)
from banxe_trading_backend.ws import orderbook_router


def _build_exchange(settings: Settings) -> ExchangePort:
    # TODO(ADR-021 governance): dispatch on settings.exchange_provider to the
    # real payment-core-bound adapter. Only "mock" is implemented.
    return InMemoryMockExchange()


def _build_market_data(settings: Settings) -> MarketDataPort:
    # TODO(ADR-021 governance): dispatch on settings.market_data_provider to the
    # real provider adapter. Only "mock" is implemented.
    return InMemoryMockMarketData()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)

    app.state.settings = settings
    app.state.exchange = _build_exchange(settings)
    app.state.market_data = _build_market_data(settings)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name, "version": __version__}

    api = settings.api_prefix
    app.include_router(orders_router, prefix=api)
    app.include_router(rate_router, prefix=api)
    app.include_router(symbols_router, prefix=api)
    app.include_router(orderbook_router)  # /ws/orderbook/{symbol}

    return app


app = create_app()
