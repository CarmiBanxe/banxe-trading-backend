# Ecosystem / Marketplace Registry — Sandbox spec (S15 / X9.4)

> **SANDBOX / MOCK-ONLY · READ-ONLY REGISTRY · INTERNAL.**
> `GET /api/v1/marketplace/providers` and `/strategies` expose a read-only
> "vitrine" of ecosystem providers / strategies / agents. **No purchases,
> subscriptions, or activations; no tokens / revenue-share / payouts; no
> entitlement, no billing, no partner-tiers, no keys, no limits.** Static fixtures
> only — no network. These are **internal terminal endpoints** — **not** a new
> external `/v1` BaaS facade (`404` there).

## Where it sits

A separate **read-only registry** layer over the already-existing providers
(LI.FI, dYdX, GMX, StakeKit, Hummingbot-based MM, quant). It is a logical catalog
of descriptive cards; **"click → trade" is NOT wired** — at most a card links to
the already-existing advisory endpoints (DSE / preview / fees / quant / mm). CORE
contracts are untouched; turning this into a live, paid marketplace is a future
operator-decision (G-sprint).

## Endpoints

### `GET /api/v1/marketplace/providers`
Optional query: `kind` (`execution` | `yield` | `mm` | `analytics`), `status`
(`sandbox` | `experimental` | `planned`). Returns `{ providers: MarketplaceProvider[] }`.

### `GET /api/v1/marketplace/strategies`
Optional query: `providerId`, `category` (`market-making` | `yield` |
`execution-routing` | `quant-analytics`), `riskProfile`
(`conservative` | `balanced` | `aggressive`), `status`, `tag`. Returns
`{ strategies: MarketplaceStrategy[] }`.

### `GET /api/v1/marketplace/strategies/{id}`
Returns one `MarketplaceStrategy`, or `404` if unknown.

## Models

`MarketplaceProvider` = `{ id, kind, name, description, status, links }` (links is a
`{label → url}` map of public docs/websites only).

`MarketplaceStrategy` = `{ id, providerId, category, name, description, riskProfile,
status, tags[] }`.

**Descriptive fields only** — no keys, no billing, no entitlement, no limits.

## Safety guarantees (asserted by tests)

- Read-only (GET only, no body); no purchase / subscription / activation path.
- No entitlement / billing / tokens / keys / limits in any card (leak-tested).
- Static fixtures, no network.
- Not reachable on the external `/v1/...` facade (`404`).
- CORE contracts (`/v1/dss/recommend`, the previews) are unchanged.

## Out of scope (future, ODR-gated)

A live / public marketplace, revenue-share, subscriptions, pay-per-use, partner
entitlement / tiering / billing, any `/v1` partner-contract change, and any
"click → trade" activation. Those are separate operator-decision sprints.
