# banxe-trading-backend

Network transport for **ExchangePort** (orders/rate, owned in `banxe-payment-core`)
plus a new **MarketDataPort** (read-only L2 order-book depth) — per
**ADR-021** (`banxe-architecture/decisions/ADR-021-exchangeport-network-transport.md`)
and HANDOFF **IL-188**.

> **Status: SKELETON.** REST/WS surface backed by **in-memory mocks** only — no
> live exchange, no real market-data provider. This lays the compiling, tested
> shape; real integration is governance-gated (see TODOs).

## Surface (ADR-021 §D2/§D3)

- **WS** `/ws/orderbook/{symbol}` — emits the FE-compatible `{type:"snapshot"|"diff", data:{bids,asks,sequence}}` envelope (decimal-string prices/quantities, I-01).
- **REST** `/api/v1`:
  - `POST /orders`, `DELETE /orders/{id}`, `GET /orders/{id}` → ExchangePort
  - `GET /rate?base=&quote=` → ExchangePort
  - `GET /symbols`, `GET /instruments/{symbol}` → MarketDataPort catalogue
- `GET /healthz` — liveness.

## Layout (backend-appropriate, not FSD)

```
src/banxe_trading_backend/
  app.py        FastAPI factory + /healthz; wires routers onto the ports
  config.py     env-only settings (no secrets)
  models.py     pydantic v2 wire types; money is decimal string (I-01)
  ports/        ExchangePort + MarketDataPort Protocols + in-memory mocks
  api/          REST routers (orders, rate, symbols)
  ws/           order-book WS endpoint
tests/          pytest: healthz, REST stubs, WS snapshot+diff, ports
```

## Canon

- **REST/WS only** — no GraphQL.
- **No Keycloak** — auth is a documented seam (backend-issued opaque token; see `config.py` / `api/deps.py` TODO), not Keycloak.
- **Decimal/I-01** — all money is a decimal string end-to-end; floats are rejected at the boundary.
- **Env-only secrets** — settings come from the environment (`BANXE_` prefix); no secrets in code.

## Governance-gated TODOs (ADR-021)

- **MarketDataPort provider** — `PrimaryExchangeAdapter` / CCXT Pro / aggregator (none hardcoded).
- **ExchangePort binding** — real adapter bound to `banxe-payment-core` (mock only here).
- **Auth mechanism** — Keycloak-free token issuance/validation.
- **Symbols / positions / balances source** — catalogue + account data not yet decided.

## Develop

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]
ruff check . && mypy && pytest
uvicorn banxe_trading_backend.app:app --reload   # local run
```
