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
from .fee_engine_port import (
    FeeComponent,
    FeeEnginePort,
    FeePreviewRequest,
    FeePreviewResponse,
    MockFeeEngine,
    ProductType,
    build_fee_provider,
)
from .lifi_quote import (
    HttpxLifiTransport,
    LifiQuoteAdapter,
    LifiQuoteTransport,
    map_lifi_quote,
)
from .market_data_port import InMemoryMockMarketData, MarketDataPort
from .market_making_port import (
    MarketMakingPort,
    MmPreviewRequest,
    MmPreviewResponse,
    MmRung,
    MockMarketMakingStrategy,
    build_mm_provider,
)
from .quote_port import MockQuoteAdapter, QuotePort
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
    "FeeEnginePort",
    "MockFeeEngine",
    "FeePreviewRequest",
    "FeePreviewResponse",
    "FeeComponent",
    "ProductType",
    "build_fee_provider",
    "MarketMakingPort",
    "MockMarketMakingStrategy",
    "MmPreviewRequest",
    "MmPreviewResponse",
    "MmRung",
    "build_mm_provider",
    "QuotePort",
    "MockQuoteAdapter",
    "LifiQuoteAdapter",
    "LifiQuoteTransport",
    "HttpxLifiTransport",
    "map_lifi_quote",
    "WalletAuthPort",
    "SiweAuthAdapter",
    "WalletAuthError",
    "DydxMarketDataAdapter",
    "DydxIndexerTransport",
    "HttpxWebsocketsTransport",
]
