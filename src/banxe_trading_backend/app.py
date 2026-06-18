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
    accounts_router,
    assets_router,
    auth_router,
    baas_dss_router,
    dss_router,
    earn_router,
    execution_router,
    fees_router,
    internal_router,
    market_making_router,
    marketplace_router,
    orders_router,
    quant_router,
    quotes_router,
    rate_router,
    risk_router,
    sandbox_gamification_router,
    sandbox_partners_router,
    sandbox_router,
    sandbox_scenarios_router,
    sandbox_sessions_router,
    symbols_router,
)
from banxe_trading_backend.config import Settings, get_settings
from banxe_trading_backend.dse import (
    DseEngine,
    MockDseEngine,
    assert_mock_only,
    foundation_profile,
    provider_profile,
    resolve_foundation,
)
from banxe_trading_backend.earn import (
    EarnRatesCatalog,
    build_earn_provider,
    build_earn_rates_catalog,
)
from banxe_trading_backend.observability import BaasMetrics
from banxe_trading_backend.ports import (
    DydxExchangeAdapter,
    DydxMarketDataAdapter,
    ExchangePort,
    FeeEnginePort,
    InMemoryMockExchange,
    InMemoryMockMarketData,
    LifiQuoteAdapter,
    MarketDataPort,
    MarketMakingPort,
    MockQuoteAdapter,
    QuantEnginePort,
    QuotePort,
    SiweAuthAdapter,
    WalletAuthPort,
    build_fee_provider,
    build_mm_provider,
    build_quant_provider,
)
from banxe_trading_backend.risk import RiskGreeksProvider, build_risk_greeks_provider
from banxe_trading_backend.services.decision_lineage import build_decision_lineage_logger
from banxe_trading_backend.services.intent_preview import build_execution_preview_provider
from banxe_trading_backend.services.sandbox_gamification import SandboxGamificationStore
from banxe_trading_backend.services.sandbox_sessions import SandboxSessionStore
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


def _build_dse(settings: Settings, *, quote: QuotePort) -> DseEngine:
    # Advisory-only (ADR-084). Only the deterministic mock ships this sprint.
    # Provider seams (sentiment/stress) selected by env (mock default); the
    # QuotePort seam is injected for future ER/slippage use (unused in mock).
    return MockDseEngine.from_settings(settings, quote=quote)


def _build_risk_greeks(settings: Settings) -> RiskGreeksProvider:
    # T7.5 read-only BaaS Greeks — advisory, sandbox/mock default (no network).
    return build_risk_greeks_provider(settings.risk_greeks_provider)


def _build_earn_rates(settings: Settings) -> EarnRatesCatalog:
    # T7.5 read-only BaaS earn rates — advisory, sandbox/mock default. The
    # catalogue composes the existing mock earn provider (no network/keys).
    provider = build_earn_provider(settings.dse_earn_provider)
    return build_earn_rates_catalog(settings.earn_rates_provider, provider)


def _build_mm(settings: Settings) -> MarketMakingPort:
    # S12 market-making advisory strategy — mock default; non-mock fails closed
    # (operator-gated: a live strategy host is ODR). Advisory/unsigned only.
    return build_mm_provider(settings.mm_provider)


def _build_fee_engine(settings: Settings) -> FeeEnginePort:
    # S13 dynamic fee engine — mock default; non-mock fails closed (operator-gated:
    # a live fee/billing source is ODR). Advisory/analytics only, no billing.
    return build_fee_provider(settings.fee_provider)


def _build_quant_engine(settings: Settings) -> QuantEnginePort:
    # S14 quant-moat engine — mock default; non-mock fails closed (operator-gated:
    # a live quant stack is ODR). Advisory analytics only, no live models.
    return build_quant_provider(settings.quant_provider)


def _build_quote(settings: Settings) -> QuotePort:
    # Provider-parameterized. Default "mock" → deterministic, no network.
    # "lifi" → public LI.FI quote API (no key; ADR-083 S6.5); constructed lazily
    # (no connection until a quote is actually requested).
    if settings.quote_provider == "lifi":
        return LifiQuoteAdapter.from_settings(settings)
    return MockQuoteAdapter()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # T8.3 safety-rail: refuse to start with a not-yet-wired live provider config
    # (ODR). Default everywhere is mock; this never trips in sandbox/CI.
    assert_mock_only(settings)
    # S10: resolve the DSE provider foundation at startup (fail-closed). Unsafe
    # tier/live combinations raise here; default tiers are all mock (CI-safe).
    foundation = resolve_foundation(settings)
    app = FastAPI(title=settings.app_name, version=__version__)

    app.state.settings = settings
    # T8.3: safe (non-secret) provider descriptor for observability.
    app.state.dse_provider_profile = provider_profile(settings)
    # S10: safe (non-secret) per-domain foundation provenance (tier + source).
    app.state.dse_foundation_profile = foundation_profile(foundation)
    app.state.exchange = _build_exchange(settings)
    app.state.market_data = _build_market_data(settings)
    app.state.quote = _build_quote(settings)
    app.state.dse = _build_dse(settings, quote=app.state.quote)
    app.state.risk_greeks = _build_risk_greeks(settings)
    app.state.earn_rates = _build_earn_rates(settings)
    # M1.6: expose the earn provider for the read-only advisory statement surface.
    app.state.earn_provider = build_earn_provider(settings.dse_earn_provider)
    app.state.wallet_auth = _build_wallet_auth(settings)
    # T8.2: internal DSE BaaS observability counters (in-process; Prometheus text).
    app.state.baas_metrics = BaasMetrics()
    # S12: market-making advisory strategy (mock default; non-mock fails closed).
    app.state.mm = _build_mm(settings)
    # S13: dynamic fee engine (advisory/analytics; mock default; fails closed).
    app.state.fee_engine = _build_fee_engine(settings)
    # S14: quant-moat engine (advisory analytics; mock default; fails closed).
    app.state.quant = _build_quant_engine(settings)
    # S16: execution-preview provider guard (mock default; non-mock fails closed).
    app.state.execution_preview_provider = build_execution_preview_provider(
        settings.execution_preview_provider
    )
    # G1L: inert, mock-safe decision-lineage audit logger (fail-closed; no provider,
    # no keys, no network, no new endpoint). Default enabled; no-op when disabled.
    app.state.decision_lineage_logger = build_decision_lineage_logger(settings)
    # SBOX-3: in-memory sandbox session store (mock-safe; no persistence, no network).
    app.state.sandbox_sessions = SandboxSessionStore()
    # SBOX-5: in-memory educational gamification store (sandbox/demo-only; no money).
    app.state.sandbox_gamification = SandboxGamificationStore()

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name, "version": __version__}

    api = settings.api_prefix
    app.include_router(auth_router, prefix=api)
    app.include_router(dss_router, prefix=api)
    app.include_router(risk_router, prefix=api)
    app.include_router(earn_router, prefix=api)
    app.include_router(accounts_router, prefix=api)
    app.include_router(assets_router, prefix=api)
    app.include_router(orders_router, prefix=api)
    # T9.1: internal DSE → unsigned execution-intent bridge (mock/sandbox-only).
    app.include_router(execution_router, prefix=api)
    app.include_router(quotes_router, prefix=api)
    app.include_router(rate_router, prefix=api)
    app.include_router(symbols_router, prefix=api)
    app.include_router(orderbook_router)  # /ws/orderbook/{symbol}
    # T8.1: external DSE BaaS sandbox facade at /v1/dss/recommend (NO api prefix).
    # Always registered; gated at request time by BANXE_DSE_BAAS_SANDBOX_ENABLED
    # (503 when off — production default serves no external DSE BaaS).
    app.include_router(baas_dss_router)
    # T8.2: internal-only observability/readiness (excluded from OpenAPI; fence at
    # ingress). /internal/health/dse-baas + /internal/metrics/dse-baas.
    app.include_router(internal_router)
    # S12: internal market-making advisory preview (mock/sandbox; NOT external /v1).
    app.include_router(market_making_router, prefix=api)
    # S13: internal dynamic fee preview (advisory/analytics; NOT external /v1).
    app.include_router(fees_router, prefix=api)
    # S14: internal quant-moat preview (advisory analytics; NOT external /v1).
    app.include_router(quant_router, prefix=api)
    # S15: internal ecosystem/marketplace registry (read-only; NOT external /v1).
    app.include_router(marketplace_router, prefix=api)
    # SBOX-1: internal unified sandbox-status surface (read-only; NOT external /v1).
    app.include_router(sandbox_router, prefix=api)
    # SBOX-2: internal deterministic demo scenarios (read-only; NOT external /v1).
    app.include_router(sandbox_scenarios_router, prefix=api)
    # SBOX-3: internal sandbox session recorder & replay (NOT external /v1).
    app.include_router(sandbox_sessions_router, prefix=api)
    # SBOX-4: internal partner sandbox pack (mock profiles; NOT external /v1).
    app.include_router(sandbox_partners_router, prefix=api)
    # SBOX-5: internal educational gamification (sandbox/demo-only; NOT external /v1).
    app.include_router(sandbox_gamification_router, prefix=api)

    return app


app = create_app()
