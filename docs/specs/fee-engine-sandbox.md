# Dynamic Fee Engine — Sandbox spec (S13 / X9.2)

> **SANDBOX / MOCK-ONLY · ADVISORY / ANALYTICS-ONLY · INTERNAL.**
> `POST /api/v1/fees/preview` returns a fee **attribution decomposition**
> (metadata) for a candidate action. **No real charges, invoices, payments, or
> billing** — this is analytics, not money. **No Lago / Orb / Stripe, no on-chain
> fee hooks, no smart-contract changes, no keys, no network.** The response is
> **unsigned / not-submitted** (`signed:false`, `submitted:false`). This is an
> **internal terminal endpoint** — it is **not** part of the external partner BaaS
> surface and is **not** exposed via the `/v1/...` facade (`404` there).

## Where it sits

A reversible **moat** seam: a `FeeEnginePort` that decomposes the fee streams of a
candidate action (DSE recommendation / intent / mm rung) into a transparent
attribution map, separating **pricing/analytics from billing**. Billing remains a
separate operator-gated concern (G-sprints), **not** in the factory train.

## Request — `FeePreviewRequest`

| Field | Type | Notes |
|---|---|---|
| `venue` | string | informational (e.g. `dydx-v4`) |
| `route` | string? | optional route hint (e.g. `lifi-spot`) |
| `productType` | enum | `spot` \| `perp` \| `earn` |
| `asset` | string | non-empty |
| `notionalUsd` | decimal-string | must be > 0 |
| `partnerTier` | string? | discount tier on platform-take fees (mock: `PRO`=0.8, `PLUS`=0.9) |
| `integratorId` | string? | informational |
| `makerRebateEligible` | bool | adds a negative `maker_rebate` rung |
| `referralCode` | string? | adds a `referral_fee` rung |

## Response — `FeePreviewResponse`

`{ mode:"sandbox-mock", signed:false, submitted:false, asset, notionalUsd,
totalFeeBps, totalFeeUsd, components[], disclaimer }`, where each `FeeComponent` is
`{ kind, bps, usd, source, note? }`.

| `kind` | mock source | applies to |
|---|---|---|
| `integrator_fee` | `LI.FI-mock` | spot (25 bps × tier) |
| `builder_code_fee` | `dYdX-builder-mock` | perp (5 bps × tier) |
| `referral_fee` | `GMX-mock` | when `referralCode` set (10 bps × tier) |
| `performance_fee` | `StakeKit-mock` | earn (200 bps × tier) |
| `maker_rebate` | `MM-rebate-mock` | when `makerRebateEligible` (−3 bps, no tier) |
| `bid_ask_spread_capture` | `spread-mock` | spot 8 / perp 5 bps |

All bps/usd are **decimal strings** (I-01). `usd = notional · bps / 10000`. Totals
are the sum of components. Zero-bps components are omitted; an unknown scheme is
ignored or annotated in `note` and never breaks the response.

## Safety guarantees (asserted by tests)

- `signed: false`, `submitted: false`, `mode: sandbox-mock` always.
- **No billing**: metadata only — no charge, invoice, payment, or settlement.
- Mock by default; a non-mock `BANXE_FEE_PROVIDER` **fails closed at startup**
  (operator-gated — a live fee/billing source is ODR).
- Deterministic, no network, no keys.
- Not reachable on the external `/v1/...` facade (`404`).
- `POST /v1/dss/recommend`, the market-making preview, and the execution-intent
  preview contracts are unchanged.

## Out of scope (future, ODR-gated)

Real billing / metering (Lago / Orb / Stripe), invoicing, on-chain fee settlement,
partner-tier *enforcement*, live fee/attribution data sources, any `/v1` partner
contract change. Those are separate operator-decision sprints.
