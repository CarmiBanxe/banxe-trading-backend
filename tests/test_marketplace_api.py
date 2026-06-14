"""Ecosystem / marketplace registry (S15 / X9.4) — internal, read-only, mock-safe.

No network. Covers the read-only providers/strategies endpoints, filtering, the
strategy-detail + 404, the no-entitlement/no-billing/no-secret guarantee,
internal-only (not on /v1), and that CORE contracts are unchanged.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.marketplace import list_providers, list_strategies

_P = "/api/v1/marketplace/providers"
_S = "/api/v1/marketplace/strategies"


def _client() -> TestClient:
    return TestClient(create_app())


# ------------------------------ providers ----------------------------------- #


def test_providers_list_and_filters() -> None:
    client = _client()
    all_ids = {p["id"] for p in client.get(_P).json()["providers"]}
    assert {"lifi", "dydx-v4", "stakekit", "hummingbot-mm"} <= all_ids
    execution = client.get(_P, params={"kind": "execution"}).json()["providers"]
    assert all(p["kind"] == "execution" for p in execution)
    planned = client.get(_P, params={"status": "planned"}).json()["providers"]
    assert all(p["status"] == "planned" for p in planned)


# ------------------------------ strategies ---------------------------------- #


def test_strategies_list_and_filters() -> None:
    client = _client()
    assert {s["id"] for s in client.get(_S).json()["strategies"]}
    yld = client.get(_S, params={"category": "yield"}).json()["strategies"]
    assert all(s["category"] == "yield" for s in yld)
    aggr = client.get(_S, params={"riskProfile": "aggressive"}).json()["strategies"]
    assert all(s["riskProfile"] == "aggressive" for s in aggr)
    by_provider = client.get(_S, params={"providerId": "hummingbot-mm"}).json()["strategies"]
    assert all(s["providerId"] == "hummingbot-mm" for s in by_provider)
    tagged = client.get(_S, params={"tag": "mm"}).json()["strategies"]
    assert all("mm" in s["tags"] for s in tagged)


def test_strategy_detail_and_404() -> None:
    client = _client()
    ok = client.get(f"{_S}/mm-avellaneda-mock")
    assert ok.status_code == 200 and ok.json()["providerId"] == "hummingbot-mm"
    assert client.get(f"{_S}/does-not-exist").status_code == 404


def test_filters_are_pure_functions() -> None:
    assert {p.id for p in list_providers(kind="yield")} == {"stakekit"}
    assert {s.id for s in list_strategies(status="planned")} == {"quant-remizov-mock"}


# ----------------------- no entitlement / billing / secrets ----------------- #


def test_no_entitlement_billing_or_secret_fields() -> None:
    client = _client()
    blob = (client.get(_P).text + client.get(_S).text).lower()
    for forbidden in (
        "billing", "price", "entitlement", "subscription", "payout", "revenue",
        "api_key", "secret", "token", "limit", "quota",
    ):
        assert forbidden not in blob
    # cards expose only descriptive fields.
    provider = client.get(_P).json()["providers"][0]
    assert set(provider) == {"id", "kind", "name", "description", "status", "links"}


# ------------------- internal-only + core contracts intact ------------------ #


def test_not_on_external_v1_facade() -> None:
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    assert client.get("/v1/marketplace/providers").status_code == 404
    assert client.get(_P).status_code == 200


def test_core_contracts_unchanged() -> None:
    client = _client()
    dss = client.post(
        "/api/v1/dss/recommend", json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"}
    )
    assert dss.status_code == 200
    recs = dss.json()["recommendations"]
    assert [r["rank"] for r in recs] == list(range(1, len(recs) + 1))
    quant = client.post(
        "/api/v1/quant/preview",
        json={"asset": "ETH", "productType": "perp", "notionalUsd": "1000", "horizonDays": 7},
    )
    assert quant.status_code == 200 and quant.json()["mode"] == "sandbox-mock"
    # marketplace responses are JSON-serialisable descriptive data (no surprises).
    json.loads(client.get(_S).text)
