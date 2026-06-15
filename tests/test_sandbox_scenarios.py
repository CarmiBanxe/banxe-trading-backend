"""Sandbox demo scenarios (SBOX-2) — internal, mock-safe, deterministic.

No network. Covers: the list (≥3 scenarios), the detail (non-empty steps, no empty
fields), determinism (double call → identical), the unsigned/no-live invariant
across every step payload, unknown-id 404, and not-on-/v1.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings

_LIST = "/api/v1/sandbox/scenarios"


def _client(settings: Settings | None = None) -> TestClient:
    return TestClient(create_app(settings))


def test_list_returns_at_least_three_scenarios() -> None:
    body = _client().get(_LIST).json()
    ids = {s["id"] for s in body["scenarios"]}
    assert {"spot-swap-demo", "perp-hedge-demo", "yield-rebalance-demo"} <= ids
    for s in body["scenarios"]:
        assert s["id"] and s["name"] and s["description"] and s["tags"]


def test_each_scenario_has_non_empty_steps() -> None:
    client = _client()
    for summary in client.get(_LIST).json()["scenarios"]:
        detail = client.get(f"{_LIST}/{summary['id']}").json()
        assert detail["id"] == summary["id"]
        assert len(detail["steps"]) >= 4
        for step in detail["steps"]:
            assert step["id"] and step["kind"] and step["title"] and step["description"]
            assert isinstance(step["payload"], dict) and step["payload"]


def test_scenarios_are_deterministic() -> None:
    client = _client()
    assert client.get(_LIST).json() == client.get(_LIST).json()
    assert (
        client.get(f"{_LIST}/spot-swap-demo").json()
        == client.get(f"{_LIST}/spot-swap-demo").json()
    )


def test_no_step_enables_live_execution_or_keys() -> None:
    client = _client()
    forbidden = ("apiKey", "api_key", "privateKey", "ownerAddress", "secret", "signature")
    for summary in client.get(_LIST).json()["scenarios"]:
        detail = client.get(f"{_LIST}/{summary['id']}")
        blob = json.dumps(detail.json())
        assert not any(tok in blob for tok in forbidden)
        for step in detail.json()["steps"]:
            # Every execution-preview step is explicitly unsigned + not submitted.
            if step["kind"] == "execution-preview":
                resp = step["payload"]["response"]
                assert resp["signed"] is False and resp["submitted"] is False


def test_unknown_scenario_is_404() -> None:
    assert _client().get(f"{_LIST}/nope-demo").status_code == 404


def test_not_on_external_v1_facade() -> None:
    client = _client(Settings(dse_baas_sandbox_enabled=True))
    assert client.get("/v1/sandbox/scenarios").status_code == 404
    assert client.get(_LIST).status_code == 200
