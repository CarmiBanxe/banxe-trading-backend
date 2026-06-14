# Market-Making Advisory Preview — Sandbox spec (S12 / X9.1)

> **SANDBOX / MOCK-ONLY · ADVISORY / PRE-PRODUCTION · INTERNAL.**
> `POST /api/v1/mm/preview` maps a market-making strategy request onto an
> **ADVISORY** quote ladder around a mid price (mock strategy). **Nothing is
> signed, submitted, or executed** — the rungs are unsigned suggestions; the
> backend holds **no keys** and contacts **no live venue**. **No SLA, no billing,
> no live chain.** This is an **internal terminal endpoint** — it is **not** part
> of the external partner BaaS surface and is **not** exposed via the `/v1/...`
> facade (it returns `404` there).

## Where it sits

A reversible **moat seam** on top of the completed CORE: a market-making
*strategy* abstraction (`MarketMakingPort`) over the existing self-custodial
`QuotePort` / `ExchangePort`, anchored by ADR-083 (Hummingbot as a **future
strategy sidecar, not a port**). It adds **no** new public endpoint and **no**
change to `POST /v1/dss/recommend` or the execution-intent preview.

## Request — `MmPreviewRequest`

| Field | Type | Notes |
|---|---|---|
| `asset` | string | e.g. `BTCUSDT` or `ETH-USDT` |
| `midPrice` | decimal-string? | optional; if absent, derived from the (mock) `ExchangePort` rate mid |
| `spreadBps` | integer | base spread per level (bps); must be > 0 |
| `levels` | integer | number of ladder levels (1..10) |
| `sizeUsd` | decimal-string | size per rung (USD); must be > 0 |

## Response — `MmPreviewResponse`

| Field | Type | Notes |
|---|---|---|
| `asset` | string | echoed |
| `mid` | decimal-string | the mid used |
| `mode` | string | always `sandbox-mock` |
| `signed` | bool | always **false** |
| `submitted` | bool | always **false** |
| `rungs` | array | `{ level, side (buy/sell), price, sizeUsd, spreadBps }` |
| `source` | string | `sandbox-mock` |
| `disclaimer` | string | self-custodial / no-execution disclosure |

The mock strategy builds a **symmetric ladder**: for each level `i`, a `buy` rung
at `mid·(1 − i·spreadBps/10000)` and a `sell` rung at `mid·(1 + i·spreadBps/10000)`,
each sized `sizeUsd`. Deterministic, no network.

## Safety guarantees (asserted by tests)

- `signed: false` and `submitted: false` always; the rungs are advisory, unsigned.
- Mock by default; a non-mock `BANXE_MM_PROVIDER` **fails closed at startup**
  (operator-gated — a live strategy host is ODR).
- No keys, no network in the path, no live venue; self-custodial (ADR-083).
- Not reachable on the external `/v1/...` facade (`404`).
- `POST /v1/dss/recommend` + the execution-intent preview contracts are unchanged.

## Out of scope (future, ODR-gated)

A live strategy host (Hummingbot sidecar), real venue keys/endpoints, client-side
signing, submission/execution, multi-venue routing, inventory/risk-aware live
quoting, SLA/billing. Per-rung `ExchangePort` unsigned-intent composition is a
later sprint (execution-preview hardening).
