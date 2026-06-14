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

## Frontend use-cases — "From recommendation to preview" (T9.2)

The terminal consumes this endpoint via an **internal Execution Intent Preview
UI** (`banxe-trading-frontend`, FSD feature `execution-intent` + widget). The
endpoint **semantics are unchanged** — the UI adds no fields and no new behaviour;
it just renders the existing response. Two entry paths:

1. **From a DSE recommendation.** The user picks a recommendation from the DSE
   widget; the UI maps `recommendation.action` (`asset`, `type`) + a user-entered
   `notionalUsd` into an `IntentPreviewRequest` (`fromRecommendation`) and calls
   this endpoint. This is the visual realization of *advice → unsigned intent*.
2. **Manual action.** The user enters `asset`, `actionType`, and `notionalUsd`
   directly.

UX flow:

```
DSE recommendation (or manual action)
   → [Preview unsigned intent]  (POST /api/v1/execution/intent-preview)
   → Execution Preview panel
        • banner: "PREVIEW ONLY — NOT EXECUTED"  (unsigned · not submitted · mock)
        • venue · side · size (amount base/quote) · orderType · reduceOnly
        • unsigned-intent state · signed:false · submitted:false
        • self-custodial disclaimer
```

**No "Execute"/"Submit" affordance** exists in the UI — it is a read-only visual
bridge between a DSE decision and a *potential* order. Field → label mapping the UI
renders (all from the existing response, no semantic change):

| Response field | Terminal label |
|---|---|
| `venue` | Venue |
| `order.side` | Side |
| `order.type` | Order type |
| `order.amount` + `order.baseAsset`/`quoteAsset` | Size |
| `order.reduceOnly` | Reduce-only |
| `intent.state` + `signed` + `submitted` | Unsigned intent |
| `tradable: false` + `reason` | "Not directly tradable (advisory-only)" |
| `disclaimer` | shown verbatim |

The UI client defaults to a **mock** provider (`VITE_EXECUTION_PROVIDER=mock`,
no network in CI); `http` targets this internal endpoint at
`VITE_EXECUTION_API_URL` (default `/api/v1`). No keys; the preview is always
unsigned and never submitted.

## Multi-venue preview (S16, additive)

The same endpoint is **additively** hardened to a multi-venue / multi-product
preview. The legacy single-venue request (above) is **unchanged**. When the request
carries `venues` / `productType` / `intentType`, the engine returns a normalized
candidate set instead of a single mapped order — **still strictly unsigned**.

Request (multi-venue; additive optional fields):

```json
{ "intentType": "swap", "asset": "ETH", "quoteAsset": "USDC", "notionalUsd": "1000",
  "venues": ["lifi", "0x"], "productType": "spot", "executionMode": "preview-only",
  "riskProfile": "balanced" }
```

- `intentType` ∈ `swap | trade | stake | hedge`; `productType` ∈ `spot | perp | earn`.
- `venues` optional — if omitted, deterministic **default venues** per product:
  spot → `lifi, 0x`; perp → `dydx-v4, gmx-v2, injective`; earn → `stakekit, aave-v3,
  lido`. An unknown venue uses mock defaults with a `note`.
- `executionMode` must be `preview-only` (else `422`). The request model is
  **`extra="forbid"`**, so any `submit` / `sign` / `live` flag **fails closed (`422`)**.

Response (additive — legacy fields stay; multi-venue adds `intentType`,
`productType`, `quoteAsset`, `candidates[]`, `bestCandidate`):

```json
{ "mode": "sandbox-mock", "signed": false, "submitted": false,
  "intentType": "swap", "productType": "spot", "asset": "ETH", "quoteAsset": "USDC",
  "bestCandidate": { "venue": "lifi", "route": "mock-lifi-route", "productType": "spot",
    "expectedPrice": "3493.70", "estimatedFeeUsd": "0.80", "estimatedSlippageBps": "18.00",
    "etaSeconds": 45, "confidence": "0.87", "signed": false, "submitted": false },
  "candidates": [ /* ...each signed:false, submitted:false... */ ],
  "disclaimer": "..." }
```

Each candidate carries **descriptive/advisory fields only** (`expectedPrice`,
`estimatedFeeUsd`, `estimatedSlippageBps`, `etaSeconds`, `confidence`, optional
`notes`) — `signed:false`, `submitted:false`. Ranking is a **deterministic mock
score** (lower fee/slippage better, lower ETA slightly better, venue suitability by
product, small `riskProfile` adjustment); `bestCandidate` is the top-scored. No
network, no real quotes/orderbooks/gas. Validation: `422` on empty asset,
`notionalUsd ≤ 0`, bad `productType`/`intentType`, empty `venues` entries, or
`executionMode != "preview-only"`. The execution-preview provider seam
`BANXE_EXECUTION_PREVIEW_PROVIDER` defaults to `mock`; any other value **fails
closed at startup** (a live execution/submission/signing provider is ODR).

## Out of scope (future, ODR-gated)

Client-side signing, submission/execution to a live chain, real multi-venue
routing, real venue keys/endpoints, SLA/billing/partner-tiering. DSE live-providers
remain PENDING/ODR (see
`banxe-architecture/docs/specs/dse-live-providers-options.md`) and are untouched
here.
