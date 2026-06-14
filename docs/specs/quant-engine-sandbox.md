# Quant-Moat Engine — Sandbox spec (S14 / X9.3)

> **SANDBOX / MOCK-ONLY · ADVISORY ANALYTICS · INTERNAL.**
> `POST /api/v1/quant/preview` returns **optional** quant signals (fair-value gap,
> stress scenario, volatility regime, flash-crash / inventory flags) as **advisory
> metadata**. **No live quant models** (no Heston / rough-Heston / Remizov / FNO /
> PINN / deep hedging), **no live price feeds, no keys, no network, no trading
> decisions** — only light deterministic logic + fixtures (we emulate signal
> *shape*). It is an **internal terminal endpoint** — **not** on the external
> `/v1/...` BaaS facade (`404` there).

## Where it sits

An **optional moat** seam: a `QuantEnginePort` that can enrich the DSE / preview /
fees / market-making flows with quant metadata. The signals are **additive**, not a
critical input — every CORE endpoint works unchanged if no quant provider is
present (mock is the default).

## Request — `QuantPreviewRequest`

| Field | Type | Notes |
|---|---|---|
| `asset` | string | non-empty (e.g. `ETH`, `BTCUSDT`) |
| `productType` | enum | `spot` \| `perp` \| `earn` \| `option` |
| `notionalUsd` | decimal-string | must be > 0 |
| `venue` | string? | informational (e.g. `dydx-v4`) |
| `horizonDays` | integer | must be > 0 (default 7) |
| `riskProfile` | string? | `conservative` \| `balanced` \| `aggressive` (informational) |
| `impliedVol` | decimal-string? | optional external IV (unused by the mock) |
| `currentSpreadBps` | decimal-string? | optional external spread (unused by the mock) |

## Response — `QuantPreviewResponse`

`{ mode:"sandbox-mock", asset, productType, notionalUsd, fairValueUsd?,
fairValueGapBps?, stressPnlDownsidePct?, volatilityRegime?, signals[], disclaimer }`
where each `QuantSignal` is `{ kind, score (∈ [-1,1]), label, note? }`.

| `kind` | meaning |
|---|---|
| `fair_value_gap` | over/under-valuation vs the mock fair value |
| `stress_scenario_score` | horizon downside-stress score |
| `volatility_regime` | `low` / `medium` / `high` classification |
| `flash_crash_guard` | elevated flash-crash risk (high regime + deep stress) |
| `inventory_risk_flag` | inventory risk (perp + high regime) |

Mock logic (deterministic): `volatilityRegime` by asset base (stables → low, BTC/ETH
→ high, else medium); `fairValueGapBps = ±regime-magnitude` (sign from a hash of
asset+product); `fairValueUsd = refPrice · (1 + gap/10000)`; `stressPnlDownsidePct`
scales lightly with `horizonDays`. All numeric fields are decimal strings (I-01).

## Safety guarantees (asserted by tests)

- `mode: "sandbox-mock"` always; signals are advisory metadata.
- **No live models / price feeds / network / keys**; deterministic.
- Mock by default; a non-mock `BANXE_QUANT_PROVIDER` **fails closed at startup**
  (a live quant stack is operator-gated — ODR).
- Not reachable on the external `/v1/...` facade (`404`).
- `POST /v1/dss/recommend`, the market-making, fee, and execution-intent previews
  are unchanged (quant is additive, never a critical input).

## Out of scope (future, ODR-gated)

A real quant stack (Remizov Solver, Heston / rough-Heston vol models, scenario
engines, FNO / PINN surrogates, deep hedging, RL market-making), live price/IV
feeds, real keys, any `/v1` partner-contract change. Those are separate
operator-decision sprints.
