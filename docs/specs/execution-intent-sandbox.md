# Execution Intent Preview — Sandbox spec (T9.1)

> **SANDBOX / MOCK-ONLY · ADVISORY / PRE-PRODUCTION · INTERNAL.**
> `POST /api/v1/execution/intent-preview` is the internal "advice → unsigned
> intent" bridge. It maps a DSE advisory action onto an **UNSIGNED** execution
> intent built by the configured `ExchangePort` (mock by default; the dYdX adapter
> builds unsigned intents too). **Nothing is signed, submitted, or executed** — the
> backend holds **no keys**, the client wallet signs client-side (out of scope).
> **No live chain, no real execution, NO SLA, NO billing, NO partner obligations.**
> This is an **internal terminal endpoint** — it is **not** part of the external
> partner BaaS surface and is **not** exposed via the `/v1/...` facade.

## Where it sits in the end-to-end trajectory

```
DSE advice (POST /v1/dss/recommend, advisory)
   → unsigned intent  (POST /api/v1/execution/intent-preview)   ← T9.1, this doc
   → client-side wallet signing                                  (out of scope, client)
   → submission / execution                                      (future, ODR-gated)
```

T9.1 implements only the **second arrow**, composing the existing advisory DSE and
the self-custodial unsigned-intent `ExchangePort`. It enables **no** new live
capability: the configured exchange stays mock by default, and the dYdX adapter
remains unsigned-intent-only (submission is operator-gated and OFF — ADR-083 S6.3b).

## Request — `IntentPreviewRequest`

| Field | Type | Notes |
|---|---|---|
| `asset` | string | e.g. `BTCUSDT` or `BTC-USDT` (split into base/quote) |
| `actionType` | enum | DSE `ActionType` (BUY / SELL / OPEN_LONG / OPEN_SHORT / CLOSE / …) |
| `notionalUsd` | decimal-string | USD notional to size the order (must be > 0) |
| `venue` | string | informational, default `mock` |
| `side` | enum? | optional override (`buy` / `sell`), e.g. for CLOSE |

## Response — `IntentPreviewResponse`

| Field | Type | Notes |
|---|---|---|
| `tradable` | bool | false for advisory-only actions (no intent) |
| `mode` | string | always `sandbox-mock` |
| `signed` | bool | always **false** |
| `submitted` | bool | always **false** |
| `reason` | string | short rationale |
| `venue` | string | echoed |
| `order` | object? | mapped `{baseAsset, quoteAsset, side, type, amount, reduceOnly}` |
| `intent` | object? | the `OrderResult` from the ExchangePort (unsigned intent in `raw`) |
| `disclaimer` | string | self-custodial / no-execution disclosure |

## Action → order mapping

| Advisory action | Order | Notes |
|---|---|---|
| `BUY`, `OPEN_LONG` | side `buy`, MARKET | |
| `SELL`, `OPEN_SHORT` | side `sell`, MARKET | |
| `CLOSE` | side `sell`, MARKET, `reduceOnly: true` | closes a long by default; override via `side` |
| `STAKE`, `HEDGE`, `HOLD`, `WAIT`, `REBALANCE`, `ADJUST_SL`, `SWAP` | — | `tradable: false`, no intent (advisory-only) |

The base amount is sized as `notionalUsd / ask`, where `ask` comes from the mock
`ExchangePort.get_rate` (deterministic, no network). `clientOrderId` /
`correlationId` are deterministic hashes of the request (idempotent, testable).

## Safety guarantees (asserted by tests)

- `signed: false` and `submitted: false` always; a preview that ever came back
  submitted is refused (`422`).
- No keys, no network, no live chain; mock/sandbox default.
- Self-custodial (ADR-083): `ownerAddress` is unset; the client signs client-side.
- Not reachable on the external `/v1/...` BaaS facade (returns 404 there).

## Out of scope (future, ODR-gated)

Client-side signing, submission/execution to a live chain, multi-venue routing,
real venue keys/endpoints, SLA/billing/partner-tiering. DSE live-providers remain
PENDING/ODR (see `banxe-architecture/docs/specs/dse-live-providers-options.md`) and
are untouched here.
