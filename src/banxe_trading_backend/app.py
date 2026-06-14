"""FastAPI application factory (ADR-021 skeleton).

Wires the REST routers + the order-book WS onto the configured ports. Adapter
selection is provider-parameterized (config); only the in-memory mocks ship in
the skeleton, so the whole surface runs deterministically with no live exchange
or market-data provider.
"""

from __future__ import annotations

from fastapi import FastAPI

from banxe_trading_backend import __version__
from banxe_trading_backend.api import (
    auth_router,
    orders_router,
    quotes_router,
    rate_router,
    symbols_router,
)
from banxe_trading_backend.config import Settings, get_settings
from banxe_trading_backend.ports import (
    DydxExchangeAdapter,
    DydxMarketDataAdapter,
    ExchangePort,
    InMemoryMockExchange,
    InMemoryMockMarketData,
    LifiQuoteAdapter,
    MarketDataPort,
    MockQuoteAdapter,
    QuotePort,
    SiweAuthAdapter,
    WalletAuthPort,
)
from banxe_trading_backend.ws import orderbook_router


def _build_wallet_auth(settings: Settings) -> WalletAuthPort:
    # SIWE/EIP-4361 (ADR-083 D4). Self-custodial — backend holds no private keys.
    return SiweAuthAdapter.from_settings(settings)


def _build_exchange(settings: Settings) -> ExchangePort:
    # Provider-parameterized. Default "mock" → deterministic, no network.
    # "dydx" → unsigned-intent adapter (ADR-083 S6.3a); no signing/submission.
    if settings.exchange_provider == "dydx":
        return DydxExchangeAdapter.from_settings(settings)
    return InMemoryMockExchange()


def _build_market_data(settings: Settings) -> MarketDataPort:
    # Provider-parameterized. Default "mock" → deterministic, no network.
    # "dydx" → public dYdX v4 Indexer (API-only; ADR-083 S6.2); constructed
    # lazily here (no connection opens until the WS/REST is actually used).
    if settings.market_data_provider == "dydx":
        return DydxMarketDataAdapter.from_settings(settings)
    return InMemoryMockMarketData()


def _build_quote(settings: Settings) -> QuotePort:
    # Provider-parameterized. Default "mock" → deterministic, no network.
    # "lifi" → public LI.FI quote API (no key; ADR-083 S6.5); constructed lazily
    # (no connection until a quote is actually requested).
    if settings.quote_provider == "lifi":
        return LifiQuoteAdapter.from_settings(settings)
    return MockQuoteAdapter()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)

    app.state.settings = settings
    app.state.exchange = _build_exchange(settings)
    app.state.market_data = _build_market_data(settings)
    app.state.quote = _build_quote(settings)
    app.state.wallet_auth = _build_wallet_auth(settings)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name, "version": __version__}

    api = settings.api_prefix
    app.include_router(auth_router, prefix=api)
    app.include_router(orders_router, prefix=api)
    app.include_router(quotes_router, prefix=api)
    app.include_router(rate_router, prefix=api)
    app.include_router(symbols_router, prefix=api)
    app.include_router(orderbook_router)  # /ws/orderbook/{symbol}

    return app


app = create_app()
