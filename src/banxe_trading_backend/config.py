"""Environment-only settings (no secrets in code — ADR-021 canon).

All values come from the process environment (prefix ``BANXE_``). Secrets
(tokens, provider credentials) are NEVER read from source or committed; they are
injected at runtime by the deployment environment.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BANXE_", extra="ignore")

    # --- service ---
    app_name: str = "banxe-trading-backend"
    api_prefix: str = "/api/v1"

    # --- provider selection ---
    # MarketDataPort provider: "mock" (default — deterministic CI, no network)
    # or "dydx" (public dYdX v4 Indexer, API-only; ADR-083 S6.2). Default stays
    # "mock" so nothing live runs in tests/CI.
    market_data_provider: str = "mock"

    # --- dYdX v4 Indexer (PUBLIC market data; API-only, NO secrets/keys) ---
    # Defaults are dYdX's public mainnet Indexer. These are PUBLIC endpoints,
    # NOT secrets. No API key / wallet is required for read-only market data.
    # AGPL: we call the public API only — no dYdX/AGPL code is vendored.
    dydx_indexer_rest_url: str = "https://indexer.dydx.trade/v4"
    dydx_indexer_ws_url: str = "wss://indexer.dydx.trade/v4/ws"
    # TODO(ADR-021 governance): choose the real ExchangePort binding to
    #   banxe-payment-core. "mock" is the only implementation in the skeleton.
    exchange_provider: str = "mock"

    # --- public (non-secret) URLs only ---
    # Real upstream URLs are injected via env at deploy time; defaults are local.
    orderbook_ws_url: str | None = None
    trade_proxy_url: str | None = None

    # --- wallet auth (SIWE / EIP-4361; ADR-083 D4 — NOT Keycloak) ---
    # Self-custodial: the backend verifies signatures and mints opaque session
    # tokens; it holds NO private keys and takes NO custody. SIWE verification is
    # signature-based — NO third-party API keys / secrets.
    #
    # `session_signing_key` signs the opaque session token (HMAC, not a JWT and
    # NOT a wallet key). It ships with a SAFE DEV DEFAULT and MUST be rotated in
    # production via BANXE_SESSION_SIGNING_KEY. This is the only auth "secret",
    # and the default is an obvious placeholder, not a real credential.
    session_signing_key: str = "dev-insecure-rotate-in-prod"
    # SIWE domain the backend expects in the signed message (binds the login).
    siwe_domain: str = "localhost"
    nonce_ttl_seconds: int = 300
    session_ttl_seconds: int = 86_400
    auth_enabled: bool = False


def get_settings() -> Settings:
    """Return process settings (constructed from the environment)."""
    return Settings()
