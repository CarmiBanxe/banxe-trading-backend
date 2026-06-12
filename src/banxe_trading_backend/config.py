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

    # --- provider selection (governance-gated; mock-only in this skeleton) ---
    # TODO(ADR-021 governance): choose the real MarketDataPort provider
    #   (PrimaryExchangeAdapter / CCXT Pro / aggregator). "mock" is the only
    #   implementation shipped in the skeleton.
    market_data_provider: str = "mock"
    # TODO(ADR-021 governance): choose the real ExchangePort binding to
    #   banxe-payment-core. "mock" is the only implementation in the skeleton.
    exchange_provider: str = "mock"

    # --- public (non-secret) URLs only ---
    # Real upstream URLs are injected via env at deploy time; defaults are local.
    orderbook_ws_url: str | None = None
    trade_proxy_url: str | None = None

    # TODO(ADR-021 / ADR-017): auth mechanism is a documented seam, NOT Keycloak.
    #   Order endpoints will require a backend-issued opaque session token,
    #   validated by an AuthPort (see ports/). Mechanism is governance-gated.
    auth_enabled: bool = False


def get_settings() -> Settings:
    """Return process settings (constructed from the environment)."""
    return Settings()
