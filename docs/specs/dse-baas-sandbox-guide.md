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

## Postman / Hoppscotch collection

Import `dse-baas-sandbox.postman_collection.json` (Postman v2.1 — also imports
into Hoppscotch). It ships an environment **"BANXE DSE Sandbox"**
(`baseUrl = https://sandbox.api.banxe.example`, `apiKey = YOUR_KEY_HERE` — a
sample) and four preconfigured `POST /v1/dss/recommend` requests (spot, perps,
earn, custom-weights).

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
