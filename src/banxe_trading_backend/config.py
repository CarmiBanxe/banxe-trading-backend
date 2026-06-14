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
    # ExchangePort provider: "mock" (default — deterministic CI) or "dydx"
    # (ADR-083 S6.3a — UNSIGNED intent construction; no signing/submission here).
    exchange_provider: str = "mock"

    # --- dYdX ExchangePort (UNSIGNED intent; self-custodial — NO keys) ---
    # The backend CONSTRUCTS unsigned order intents; the client wallet signs.
    # It does NOT submit signed txns in this step — live submission is
    # OPERATOR-GATED (real node endpoint + wallet), deferred to S6.3b.
    dydx_subaccount_number: int = 0
    # Builder Codes (revenue-share) — OPERATOR-GATED. Attached ONLY when BOTH a
    # non-empty address AND a positive fee are set; otherwise no builder fields.
    # NO real address/fee is committed (defaults: unset / 0).
    dydx_builder_address: str | None = None
    dydx_builder_fee_ppm: int = 0
    # Live submission (S6.3b) — OPERATOR-GATED, DEFAULT OFF. Submission requires
    # BOTH dydx_submit_enabled AND a syntactically valid dydx_node_url; otherwise
    # the backend only returns unsigned intents (submitted:false) and makes NO
    # network call. NO real node endpoint is committed (defaults: false / unset).
    dydx_submit_enabled: bool = False
    dydx_node_url: str | None = None
    # Submission HTTP timeout (seconds) — env-only, safe default. No endpoint here.
    dydx_submit_timeout_s: float = 10.0

    # --- QuotePort (LI.FI aggregator) — env-gated, mock default (S6.5) ---
    # Default provider is the in-memory mock (no network in CI/dev). The LI.FI
    # adapter activates only when quote_provider == "lifi". The base URL is the
    # PUBLIC LI.FI API (no key required for public quotes).
    quote_provider: str = "mock"
    lifi_base_url: str = "https://li.quest/v1"
    # OPTIONAL seams — OPERATOR-GATED, default DISABLED. No real values committed.
    # lifi_api_key: unused this sprint (seam only — never sent in S6.5).
    # integrator + fee attach to LI.FI requests ONLY when BOTH are set (id present
    # AND fee_bps > 0); otherwise no integrator/fee params are sent.
    lifi_api_key: str = ""
    lifi_integrator: str = ""
    lifi_fee_bps: int = 0
    lifi_timeout_s: float = 10.0

    # --- DSE (Decision Support Engine) — advisory-only, mock default (T7.1) ---
    # ADVISORY-ONLY (ADR-084): no auto-execution, no signing, no key custody,
    # no gamification. Only "mock" is implemented this sprint. Real sentiment
    # (MiroFish) / stress (MicroFish CMS-VAE) providers are separate, env-gated
    # sprints — these are seams, default "mock", no endpoints/keys committed.
    dse_provider: str = "mock"
    dse_sentiment_provider: str = "mock"
    dse_stress_provider: str = "mock"
    # Risk (Greeks/VaR/PnL) + earn (yields) advisory seams — mock by default
    # (T7.3). Real providers are OPERATOR-GATED; no keys/network in code.
    dse_risk_provider: str = "mock"
    dse_earn_provider: str = "mock"

    # --- DSE provider-layer & future live-provider seams (T8.3) ---
    # OVERALL provider mode. Only "mock" is implemented and is the default; any
    # other value ("sandbox-live" / "prod-live") is OPERATOR-GATED (ODR) and the
    # app refuses to start with it (no live impl exists). T8.3 adds wiring +
    # safety-rails ONLY — it activates no live provider and changes no behaviour.
    dse_provider_mode: str = "mock"
    # Market-data source feeding DSE risk metrics (volatility/VaR/drawdown/liq).
    # Mock by default; future live source is ODR-gated.
    dse_market_provider: str = "mock"
    # Placeholder live API-key / base-URL seams per domain. These are EMPTY by
    # default and MUST stay empty in code — any real value belongs to deployment
    # env and is OPERATOR DECISION (ODR) + compliance (MiCA / BaaS). They are
    # unused while the mode is "mock" (no live client reads them).
    dse_market_api_key: str = ""
    dse_market_base_url: str = ""
    dse_sentiment_api_key: str = ""
    dse_sentiment_base_url: str = ""
    dse_stress_api_key: str = ""
    dse_stress_base_url: str = ""
    dse_earn_api_key: str = ""
    dse_earn_base_url: str = ""

    # --- DSE provider foundation tiers (Sprint S10) ---
    # Per-domain provider tier: "mock" (default, deterministic), "stub" (neutral
    # fixtures for contract/fallback tests), or "live-ready" (CI-safe INERT
    # scaffold — selectable but performs NO network and needs NO credentials).
    # Default everywhere is mock; runtime stays mock-first and CI-safe.
    dse_market_tier: str = "mock"
    dse_sentiment_tier: str = "mock"
    dse_stress_tier: str = "mock"
    # Master live switch. Default OFF. When OFF, a "live-ready" tier runs inert.
    # When ON, live activation is attempted and FAILS CLOSED unless a real network
    # adapter + credentials are wired — neither exists this sprint (OPERATOR
    # DECISION REQUIRED + compliance, MiCA / BaaS). Never set true in code/CI.
    dse_live_allowed: bool = False

    # --- Market-making advisory seam (S12 / X9.1) — mock-only, OFF-by-default ---
    # Strategy provider for POST /api/v1/mm/preview. Only "mock" is wired and is
    # the default; any other value is OPERATOR-GATED (a live strategy host such as
    # a Hummingbot sidecar is ODR) and fails closed at startup. Advisory/unsigned;
    # no live venue, no keys, no execution.
    mm_provider: str = "mock"

    # --- Dynamic fee engine seam (S13 / X9.2) — advisory/analytics, mock-only ---
    # Fee-attribution provider for POST /api/v1/fees/preview. Only "mock" is wired
    # and default; any other value is OPERATOR-GATED (live fee/billing source is
    # ODR) and fails closed at startup. Analytics-only: NO real billing/charges.
    fee_provider: str = "mock"

    # --- Quant-moat advisory seam (S14 / X9.3) — analytics, mock-only ---
    # Quant-analytics provider for POST /api/v1/quant/preview. Only "mock" is wired
    # and default; any other value is OPERATOR-GATED (a live quant stack — Remizov /
    # Heston / FNO / deep hedging — is ODR) and fails closed at startup. Advisory
    # analytics only: no live models, no live price feeds, no trading decisions.
    quant_provider: str = "mock"

    # --- read-only Risk/Earn BaaS sandbox surface (T7.5) ---
    # GET /v1/risk/greeks + GET /v1/earn/rates — advisory, READ-ONLY, sandbox.
    # Mock by default (deterministic, no network/keys). Real providers are
    # OPERATOR-GATED future sprints; these seams stay empty/no-op this sprint.
    risk_greeks_provider: str = "mock"
    earn_rates_provider: str = "mock"

    # --- DSE sandbox decision-trace (T7.8) — observability/debug, OFF by default ---
    # When True (sandbox/dev ONLY), AND the request carries the X-Banxe-Dse-Debug
    # header, POST /api/v1/dss/recommend attaches an OPTIONAL decisionTrace that
    # reconstructs the mock decision path (inputs, normalized features, utility,
    # enrichment) by traceId. Double-gated; default OFF so production partners
    # never receive it. The trace carries NO secrets/keys/endpoints — only
    # request-derived data + mock model metadata. Does NOT change utility/ranking.
    dse_debug_enabled: bool = False

    # --- DSE BaaS sandbox facade (T8.1) — external advisory endpoint, OFF default ---
    # When True (sandbox/dev deployments ONLY), the external BaaS facade
    # POST /v1/dss/recommend is served as a thin, advisory-only, mock-only proxy
    # over the SAME internal DSE engine. Default OFF: production environments serve
    # NO external DSE BaaS (the facade returns 503 "sandbox disabled"). Deployment
    # MUST additionally fence this to sandbox/dev hosts at the ingress/host layer.
    # Advisory-only: NO execution, NO signing, NO billing, NO partner keys.
    dse_baas_sandbox_enabled: bool = False

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
