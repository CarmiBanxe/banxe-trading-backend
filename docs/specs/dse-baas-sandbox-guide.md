# BANXE DSE BaaS — Sandbox & Developer Guide (T7.4)

The **Decision Support Engine (DSE)** advisory API for BaaS/TaaS partners. One
endpoint — `POST /v1/dss/recommend` — returns ranked, explainable recommendations
with **Risk** (Greeks / VaR / PnL) and **Earn** (yield) metrics.

> **Advisory-only / self-custodial.** The DSE **never executes orders, signs
> transactions, or holds keys**. It returns numbers + explanations; your app
> prompts the user to confirm and place any order in their own flow. This is
> **decision-support, not investment advice and not execution** (MiCA / MiFID II).
> **Sandbox responses are mock / simulated data — do not use them in a real-money
> production path.** No real keys, no production rate limits, no gamification.

## DSE advisory API vs Trading Core API

| | DSE Advisory API (this) | Trading Core API |
|---|---|---|
| Purpose | explainable recommendations + Risk/Earn metrics | quotes / order intents / submission |
| Executes orders? | **No** | yes (self-custodial; client signs) |
| Holds keys? | **No** | no (signs nothing; relays signed tx) |
| Sandbox data | mock / simulated | mock by default |
| Tier | BaaS Tier 2 (advisory) | Tier 2 (execution) |

## Quick start

1. Sign up for the **Free Sandbox** tier (self-serve) and copy your sandbox key.
2. Set `baseUrl = https://sandbox.api.banxe.example` and your key
   (`DSE_SANDBOX_API_KEY`, a **sample placeholder** here — replace with yours).
3. Call `POST {baseUrl}/v1/dss/recommend`. Render the recommendations and the
   Risk/Earn metrics. **Never auto-execute** — let the user confirm manually.

```bash
curl -sS -X POST "$DSE_SANDBOX_BASE_URL/v1/dss/recommend" \
  -H "content-type: application/json" \
  -H "authorization: Bearer $DSE_SANDBOX_API_KEY" \
  -d '{"asset":"BTCUSDT","portfolioValueUsd":"10000","riskProfile":"balanced"}'
```

The full request/response schema is the OpenAPI in `dse-baas-api.yaml`
(+ `dse-utility-api.yaml`). All monetary/metric fields are **decimal strings**.

## Enabling the DSE BaaS sandbox facade (T8.1)

The external `POST /v1/dss/recommend` is a **thin, advisory-only, mock-only**
facade over the same internal DSE engine that serves the terminal. It is
**sandbox-gated** and **OFF by default** — production serves no external DSE BaaS.

1. **Enable it (sandbox/dev only):** set the env flag and start the service:

   ```bash
   export BANXE_DSE_BAAS_SANDBOX_ENABLED=true
   uvicorn banxe_trading_backend.app:app
   ```

   With the flag **off** (production default), every call to `/v1/dss/recommend`
   returns **`503 {"detail":"DSE BaaS sandbox is disabled"}`**. Deployments should
   additionally fence this route to sandbox/dev at the **ingress/host** layer.

2. **Send a request** (no partner key needed in sandbox — mock data only):

   ```bash
   curl -sS -X POST "http://localhost:8000/v1/dss/recommend" \
     -H "content-type: application/json" \
     -d '{"asset":"BTCUSDT","portfolioValueUsd":"10000","riskProfile":"balanced",
          "currentPositions":[{"asset":"BTCUSDT","sizeUsd":"8000","side":"long"}],
          "includeSentiment":true,"includeStressTests":true}'
   ```

3. **Interpret the response:**
   - `recommendations[]` — ranked, each with `utilityScore`, Kelly/Half-Kelly
     sizing, `riskMetrics`, and (earn actions) `earnMetrics`.
   - `recommendations[].utilityBreakdown` + `topDriver` — *why* the score (the
     signed terms sum to `utilityScore`); render a waterfall / why-this-rank panel.
   - `analyticsContext` — portfolio Greeks summary + informational earn alternatives.
   - `traceId` — deterministic id for correlation.
   - `decisionTrace` — present **only** when the debug gate is *also* on
     (`BANXE_DSE_DEBUG_ENABLED=true` **and** header `X-Banxe-Dse-Debug: true`);
     otherwise `null`. It reconstructs the full mock decision path for debugging.

   ```bash
   # full decision-trace (dev-only): both gates on
   BANXE_DSE_BAAS_SANDBOX_ENABLED=true BANXE_DSE_DEBUG_ENABLED=true \
     uvicorn banxe_trading_backend.app:app
   curl -sS -X POST "http://localhost:8000/v1/dss/recommend" \
     -H "content-type: application/json" -H "X-Banxe-Dse-Debug: true" \
     -d '{"asset":"BTCUSDT","portfolioValueUsd":"10000"}'
   ```

**Advisory-only / no execution:** the facade ranks and explains; it never
executes, signs, stakes, or holds keys. **No SLA, no billing, no rate limits**
(future ODR). Self-custodial — the user confirms and signs any order themselves.

## Analytics enrichment (additive, informational) — T7.6

`POST /v1/dss/recommend` **internally** consults the same sandbox Risk Greeks and
Earn rates analytics (the T7.5 services) to make its advisory reasoning richer.
**No new endpoint, no contract break** — the response simply gains **optional,
additive** fields you may render or ignore. They are **sandbox/mock-derived and
informational only** — not execution, not a promise of return.

New optional fields:

- `analyticsContext.greeksSummary` — portfolio-level Greeks for your net position
  in the asset, plus a qualitative `directionalExposure` (low / elevated / high)
  and human-readable `notes`. Present only when `currentPositions` give enough
  context; otherwise `null` (graceful degrade).
- `analyticsContext.earnAlternatives` — an informational "where idle capital could
  sit" yield comparison (sorted by APY).
- `recommendations[].riskNotes` — Greeks-derived advisory notes on tradable ideas.
- `recommendations[].alternatives` — earn alternatives surfaced next to
  capital-preservation actions (HOLD / WAIT / HEDGE / STAKE).

**Before** (request without positions) → `analyticsContext.greeksSummary` is
`null`; recommendations carry no `riskNotes`/`alternatives`.

**After** (request *with* `currentPositions`):

```json
{
  "recommendations": [
    { "rank": 1, "action": { "type": "OPEN_LONG", "category": "perp", "asset": "BTCUSDT" },
      "riskNotes": ["High directional exposure (delta 0.8000) on BTCUSDT; consider hedging or sizing down."],
      "...": "..." },
    { "rank": 5, "action": { "type": "HOLD", "category": "meta", "asset": "BTCUSDT" },
      "alternatives": [ { "asset": "USDC", "protocol": "mock-lending", "apyPct": "5.0000",
        "lockupDays": 0, "riskBand": "low", "source": "sandbox-mock" } ] }
  ],
  "analyticsContext": {
    "greeksSummary": { "directionalExposure": "high", "side": "long",
      "greeks": { "delta": "0.8000", "gamma": "0.0160", "vega": "0.0800", "theta": "-0.0080", "rho": "0.0080" },
      "notionalUsd": "8000.00", "notes": ["..."], "source": "sandbox-mock" },
    "earnAlternatives": [ { "asset": "USDC", "apyPct": "5.0000", "riskBand": "low", "source": "sandbox-mock" } ],
    "analyticsVersion": "dss-analytics-enrichment-0.1.0", "source": "sandbox-mock"
  }
}
```

**Treat these fields as informational only:** show the notes/alternatives in your
UI as context; **do not** auto-execute, auto-hedge, or auto-stake. The endpoint
remains advisory and self-custodial, and the public BaaS surface is **unchanged**.

## Explainability & traceability — T7.7

`POST /v1/dss/recommend` exposes **why** each recommendation got its score and a
stable id for the response. **No new endpoint, no contract break** — these are
**optional, additive** fields, and they **do not change** the utility score or the
ranking (they decompose the *existing* math `U_a = w1·ER − w2·σ − w3·VaR99 −
w4·DD + w5·Liq`).

- `recommendations[].utilityBreakdown` — the five signed terms behind the score.
  Each component has `factor`, `value`, `weight`, `contribution` (signed) and
  `direction`. **The contributions sum exactly to `utilityScore`** — render a
  waterfall / "why this rank" panel from it.
- `recommendations[].topDriver` — the factor with the largest absolute
  contribution (the dominant reason).
- `traceId` — **deterministic**: the same request (canonical inputs) always
  yields the same id (`dss-<hash>`). Use it to correlate logs / support tickets
  and to dedupe identical advisory calls.
- `explanationVersion` — version tag of the explainability layer (traceability).

```json
{
  "recommendations": [
    { "rank": 1, "action": { "type": "BUY", "category": "spot", "asset": "BTCUSDT" },
      "utilityScore": "0.842948", "topDriver": "liquidity",
      "utilityBreakdown": [
        { "factor": "expectedReturn", "value": "0.060000", "weight": "1.0", "contribution": "0.060000", "direction": "positive" },
        { "factor": "volatility", "value": "0.030000", "weight": "1.0", "contribution": "-0.030000", "direction": "negative" },
        { "factor": "var99", "value": "0.069789", "weight": "1.0", "contribution": "-0.069789", "direction": "negative" },
        { "factor": "drawdown", "value": "0.040000", "weight": "1.0", "contribution": "-0.040000", "direction": "negative" },
        { "factor": "liquidity", "value": "0.950000", "weight": "1.0", "contribution": "0.950000", "direction": "positive" }
      ] }
  ],
  "traceId": "dss-50b286aba2c567a7",
  "explanationVersion": "dss-explain-0.1.0"
}
```

These fields are **informational/advisory only** — they explain the model, they
do not authorize execution. The breakdown is mock/sandbox-derived like the rest
of this build.

## Decision trace (DEV-ONLY observability) — T7.8

For sandbox debugging, the engine can attach a `decisionTrace` that lets you
reconstruct the **whole mock decision path** (inputs → normalized features →
`utilityBreakdown` → enrichment) by `traceId`. It is **double-gated and OFF by
default** — **production partners never receive it**:

1. **Operator env flag** `BANXE_DSE_DEBUG_ENABLED=true` (sandbox/dev deployments
   only), **and**
2. **Per-request opt-in header** `X-Banxe-Dse-Debug: true`.

With either gate closed, `decisionTrace` is `null`/absent and the response is
exactly the production contract.

```bash
curl -sS -X POST "$DSE_SANDBOX_BASE_URL/v1/dss/recommend" \
  -H "content-type: application/json" \
  -H "X-Banxe-Dse-Debug: true" \
  -d '{"asset":"BTCUSDT","portfolioValueUsd":"10000",
       "currentPositions":[{"asset":"BTCUSDT","sizeUsd":"8000","side":"long"}]}'
```

```json
{
  "decisionTrace": {
    "traceId": "dss-50b286aba2c567a7",
    "riskProfile": "balanced",
    "weights": { "w1ExpectedReturn": "1.0", "w2Volatility": "1.0", "w3Var99": "1.0", "w4Drawdown": "1.0", "w5Liquidity": "1.0" },
    "riskProvider": "MockRiskMetricsProvider", "earnProvider": "MockEarnRatesProvider",
    "sentimentProvider": "MockSentimentProvider", "stressProvider": "MockStressProvider",
    "enrichmentApplied": true,
    "steps": [
      { "rank": 3, "actionType": "STAKE", "actionCategory": "earn",
        "rawExpectedReturn": "0.050000", "earnYieldPct": "3.5000",
        "effectiveExpectedReturn": "0.085000", "volatility": "0.010000",
        "var99": "0.023263", "var99Source": "risk-provider",
        "drawdown": "0.010000", "liquidity": "0.600000", "utilityScore": "..." }
    ],
    "note": "Sandbox debug trace — ... Contains NO production secrets, keys, or live data. dev/sandbox only."
  }
}
```

**Security & scope:** the trace carries **only** request-derived data, mock model
metadata, and provider **class names** (e.g. `MockRiskMetricsProvider`) — **never**
keys, secrets, endpoints, or env values. It is observability, **not** execution,
and it **does not change** utility or ranking. Correlate by `traceId` (the same
deterministic id as the response).

## Walkthroughs

### 1. Risk card + recommendation (neobank)

A neobank shows the user a **risk snapshot** plus one or two recommendations —
**no auto-execution**.

Request (spot, balanced):

```json
{ "asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced",
  "includeSentiment": true, "includeStressTests": true }
```

Response (excerpt — read `riskMetrics` + `reasons`, render a card):

```json
{
  "recommendations": [
    { "rank": 1, "action": { "type": "HOLD", "category": "meta", "asset": "BTCUSDT" },
      "utilityScore": "1.000000", "halfKellySizePct": "0.0000",
      "riskMetrics": { "greeks": { "delta": "0", "gamma": "0", "vega": "0", "theta": "0", "rho": "0" },
        "var99Pct": "0.0000", "ddPct": "0.0000", "unrealizedPnlPct": "0.0000",
        "unrealizedPnlUsd": "0.00", "liquidityScore": "1.0000" },
      "reasons": "Maintain current exposure; take no new risk. VaR99 0%, delta 0." }
  ],
  "sentiment": { "score": "0.35", "news": "0.40", "onchain": "0.30", "social": "0.35", "modelVersion": "mock-sentiment-0.1.0" },
  "modelVersions": { "pricing": "...", "sentiment": "...", "kelly": "...", "stress": "..." },
  "disclaimer": "Advisory only — not investment advice ...",
  "asOf": "2026-...Z"
}
```

UX: show a "Use this" affordance that **pre-fills your own order form** — the user
reviews and submits. Never place the order automatically.

### 2. Yield comparison panel (wallet / fintech app)

A wallet uses **only `earnMetrics`** to help the user compare protocols, then
hands the chosen action to **its own execution layer** (not BANXE).

Request (earn, conservative):

```json
{ "asset": "USDC", "portfolioValueUsd": "50000", "riskProfile": "conservative" }
```

Read each earn-category recommendation's `earnMetrics`
(`currentYieldPct`, `protocol`, `chain`, `lockupDays`, `variableRate`,
`riskSummary`) and render a comparison. The variable-rate flag and `riskSummary`
must be shown — yields are **estimates, not a promise of return**.

### 3. Perps with tighter risk

```json
{ "asset": "ETHUSDT", "portfolioValueUsd": "25000", "riskProfile": "aggressive",
  "currentPositions": [{ "asset": "ETHUSDT", "sizeUsd": "5000", "side": "long" }] }
```

Use `riskMetrics.var99Pct` and `riskMetrics.greeks` for a tighter risk display;
`unrealizedPnlUsd/Pct` reflects the provided position.

## Risk API — sandbox Greeks (read-only)

`GET /v1/risk/greeks` returns **portfolio-level Greeks** (Delta / Gamma / Vega /
Theta / Rho) for a target asset / net notional. **Read-only advisory analytics** —
not execution, not investment advice (MiCA / MiFID II). Sandbox values are
deterministic mock data flagged `source: "sandbox-mock"`. The future Risk
endpoints (`/v1/risk/var`, `/v1/risk/stress`, `/v1/risk/pnl`) are **not** in this
sandbox.

```bash
curl -sS "$DSE_SANDBOX_BASE_URL/v1/risk/greeks?asset=BTCUSDT&portfolioValueUsd=10000&positionUsd=5000&side=long" \
  -H "authorization: Bearer $DSE_SANDBOX_API_KEY"
```

```json
{ "asset": "BTCUSDT", "notionalUsd": "5000.00", "side": "long",
  "greeks": { "delta": "0.5000", "gamma": "0.0100", "vega": "0.0500",
    "theta": "-0.0050", "rho": "0.0050" },
  "source": "sandbox-mock", "asOf": "2026-...Z",
  "disclaimer": "Advisory analytics only — sandbox mock data ..." }
```

**UX:** render a **Greeks panel / risk badge** next to the position — show the
`source: sandbox-mock` flag and the disclaimer. No "auto-hedge", no auto-execution,
no gamification.

## Earn API — sandbox rates (read-only)

`GET /v1/earn/rates` returns a **current-yield comparison** ("rate cards") across
a basket of assets. **Read-only** — there is **no stake / unstake and no order
placement**. Yields are estimates / simulations flagged `source: "sandbox-mock"`,
not a promise of return.

```bash
curl -sS "$DSE_SANDBOX_BASE_URL/v1/earn/rates?assets=ETH&assets=USDC" \
  -H "authorization: Bearer $DSE_SANDBOX_API_KEY"
```

```json
{ "rates": [
    { "asset": "ETH", "protocol": "mock-liquid-staking", "apyPct": "4.2000",
      "lockupDays": 0, "variableRate": true, "riskBand": "medium", "source": "sandbox-mock" },
    { "asset": "USDC", "protocol": "mock-lending", "apyPct": "5.0000",
      "lockupDays": 0, "variableRate": true, "riskBand": "low", "source": "sandbox-mock" } ],
  "source": "sandbox-mock", "asOf": "2026-...Z",
  "disclaimer": "Advisory analytics only — sandbox mock yields ..." }
```

**UX:** render a **comparison table** (asset / protocol / APY / lockup / risk
band). Always show `variableRate` and the disclaimer. **No** "stake now" button,
leaderboard, or copy-trading — the user acts in their own self-custodial flow.

## Postman / Hoppscotch collection

Import `dse-baas-sandbox.postman_collection.json` (Postman v2.1 — also imports
into Hoppscotch). It ships an environment **"BANXE DSE Sandbox"**
(`baseUrl = https://sandbox.api.banxe.example`, `apiKey = YOUR_KEY_HERE` — a
sample) and preconfigured requests: four `POST /v1/dss/recommend` (spot, perps,
earn, custom-weights) plus the two read-only sandbox endpoints
`GET /v1/risk/greeks` and `GET /v1/earn/rates`.

## Python client skeleton

`clients/python/dse_client.py` is a copy-pasteable, dependency-light wrapper
(`DseClient(base_url, api_key=..., timeout=...).recommend(request)`). It is a
documentation skeleton — **not** published to PyPI.

## Compliance & UX guardrails (partner checklist)

- **Sandbox data is simulated** — never use it in a real-money production path.
- **Recommended pattern:** *recommendation → user manually confirms the order.*
  **No** auto-execution, copy-trading, social-feed / leaderboard, streaks, or
  tournaments for DSE on this phase (out of scope per ADR-084 / ADR-085).
- **Disclaimers:** surface the response `disclaimer`; state that Risk/Earn figures
  are estimates/simulations, not guarantees.
- **Suitability & jurisdiction:** run your own MiCA CASP / MiFID II suitability
  checks and jurisdiction-specific restrictions before showing or acting on
  recommendations. See the master-plan MiCA/MiFID section.
- **Self-custodial:** the user signs every transaction in their own wallet.

## Operator-gated (NOT in sandbox)

Real partner keys (Kong gateway), production rate limits, live execution, real
risk/earn data providers (StakeKit / Aave / risk-data / MiroFish / MicroFish),
and any white-label / revenue terms are **OPERATOR DECISION REQUIRED** — env-only,
never in code, and out of scope for the sandbox.
