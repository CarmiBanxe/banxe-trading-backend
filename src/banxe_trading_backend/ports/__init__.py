"""Hexagonal ports + adapters (ADR-021 / ADR-083)."""

from .dydx_exchange import (
    BuilderCodes,
    DydxExchangeAdapter,
    DydxMarketParams,
    DydxSubmissionTransport,
    HttpxSubmissionTransport,
    calculate_quantums,
    calculate_subticks,
)
from .dydx_market_data import (
    DydxIndexerTransport,
    DydxMarketDataAdapter,
    HttpxWebsocketsTransport,
)
from .exchange_port import (
    ComplianceBlock,
    ExchangeError,
    ExchangePort,
    ExchangeUnavailable,
    IdempotencyConflict,
    InMemoryMockExchange,
    InsufficientBalance,
    PartialFillTimeout,
    StaleRate,
    ValidationError,
)
from .market_data_port import InMemoryMockMarketData, MarketDataPort
from .wallet_auth_port import SiweAuthAdapter, WalletAuthError, WalletAuthPort

__all__ = [
    "ExchangePort",
    "InMemoryMockExchange",
    "DydxExchangeAdapter",
    "DydxMarketParams",
    "BuilderCodes",
    "DydxSubmissionTransport",
    "HttpxSubmissionTransport",
    "calculate_quantums",
    "calculate_subticks",
    "ExchangeError",
    "ValidationError",
    "IdempotencyConflict",
    "StaleRate",
    "ExchangeUnavailable",
    "InsufficientBalance",
    "ComplianceBlock",
    "PartialFillTimeout",
    "MarketDataPort",
    "InMemoryMockMarketData",
    "WalletAuthPort",
    "SiweAuthAdapter",
    "WalletAuthError",
    "DydxMarketDataAdapter",
    "DydxIndexerTransport",
    "HttpxWebsocketsTransport",
]
