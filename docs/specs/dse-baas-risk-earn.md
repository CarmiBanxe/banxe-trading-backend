# BaaS — Risk & Earn advisory via `POST /v1/dss/recommend` (T7.3)

Developer guide for BaaS/TaaS partners. The DSE endpoint returns **explainable,
advisory-only** recommendations enriched with **Risk** (Greeks / VaR / PnL) and
**Earn** (yield) metrics — so partners can build a *risk card*, a *yield
comparison*, or a *decision assistant* **without implementing auto-trading**.

> **Advisory-only / self-custodial.** This endpoint never executes orders, signs
> transactions, or holds keys. `riskMetrics` and `earnMetrics` are **estimates /
> simulations, not guarantees of return**. No new Risk/Earn execution endpoints
> are introduced (the Phase-2 `GET /v1/risk/*` and `POST /v1/orders/earn/*` are
> out of scope here). Per MiCA / MiFID II, advisory and execution stay separate.
> No casino / gamification / leaderboards. Real risk/earn data providers and any
> live execution are **OPERATOR DECISION REQUIRED** (keys, Tier-2/3 enablement).

## Partner use-cases (advisory surfaces only)

- **Risk card** — show `riskMetrics` (Greeks summary, VaR99, drawdown, unrealized
  PnL, liquidity) next to a position; no order is placed.
- **Yield comparison** — render `earnMetrics` (current yield, protocol, chain,
  lockup, variable flag, risk summary) for earn-category recommendations.
- **Decision assistant** — rank actions by `utilityScore` and explain via
  `reasons`; any "Use this" button only **pre-fills** the partner's own order /
  earn form — it must not auto-execute.

## Request (example)

```json
{
  "asset": "BTCUSDT",
  "portfolioValueUsd": "10000",
  "riskProfile": "balanced",
  "currentPositions": [{ "asset": "BTCUSDT", "sizeUsd": "1000", "side": "long" }],
  "includeStressTests": true,
  "includeSentiment": true
}
```

## Response (excerpt — `riskMetrics` + `earnMetrics` filled)

```json
{
  "recommendations": [
    {
      "rank": 1,
      "action": { "type": "STAKE", "category": "earn", "asset": "BTCUSDT" },
      "utilityScore": "0.642000",
      "kellySizePct": "...",
      "halfKellySizePct": "...",
      "riskMetrics": {
        "greeks": { "delta": "0.2", "gamma": "0", "vega": "0", "theta": "0.01", "rho": "0" },
        "var99Pct": "2.3263",
        "ddPct": "1.0000",
        "unrealizedPnlPct": "0.0000",
        "unrealizedPnlUsd": "0.00",
        "liquidityScore": "0.6000"
      },
      "earnMetrics": {
        "currentYieldPct": "3.5000",
        "protocol": "mock-stakekit",
        "chain": "ethereum",
        "lockupDays": 7,
        "variableRate": true,
        "riskSummary": "Wrapped/liquid staking; smart-contract + slashing risk."
      },
      "reasons": "Yield with low volatility ... VaR99 2.3263%, delta 0.2. Yield 3.5000% (mock-stakekit, ethereum)."
    }
  ],
  "sentiment": { "score": "0.35", "...": "..." },
  "modelVersions": { "pricing": "mock-pricing-0.1.0", "sentiment": "mock-sentiment-0.1.0", "kelly": "kelly-0.1.0", "stress": "mock-stress-0.1.0" },
  "disclaimer": "Advisory only — not investment advice ...",
  "asOf": "2026-…Z"
}
```

`earnMetrics` is present only on **earn-category** actions; `riskMetrics` is
present on every recommendation. All monetary / metric fields are **decimal
strings (I-01)** — never floats.

## Field mapping (advisory-only re-use of Risk/Earn API shapes)

The field shapes deliberately mirror the master-plan Risk API (`greeks`,
`var99Pct`, `pnl`) and the Earn API (`currentYieldPct`, `protocol`, `lockupDays`)
so a partner can later adopt the dedicated endpoints with no remapping — but in
T7.3 the data is served **only** through this advisory DSE endpoint, mock by
default.
