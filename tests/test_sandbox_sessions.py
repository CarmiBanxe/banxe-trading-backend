"""Sandbox session recorder & replay (SBOX-3) — internal, mock-safe.

No network. Covers: create, append step, finish (finishedAt + notes), list with
limit/offset, get-by-id, unknown-id 404, not-on-/v1, no live/keys, and the optional
G1L link via the X-Banxe-Sandbox-Session-Id header.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.services.sandbox_sessions import SANDBOX_SESSION_HEADER

_BASE = "/api/v1/sandbox/sessions"


def _client(settings: Settings | None = None) -> TestClient:
    return TestClient(create_app(settings))


def _create(client: TestClient, **kw: object) -> dict:
    payload = {"scenarioId": "spot-swap-demo", "title": "Demo", "description": "d", **kw}
    return client.post(_BASE, json=payload).json()


def test_create_session() -> None:
    body = _create(_client())
    assert body["id"] and body["startedAt"]
    assert body["finishedAt"] is None
    assert body["scenarioId"] == "spot-swap-demo"
    assert body["steps"] == [] and body["notes"] is None


def test_append_step_updates_summary() -> None:
    client = _client()
    sid = _create(client)["id"]
    step = {"scenarioId": "spot-swap-demo", "stepId": "step-1-dse", "layer": "DSE"}
    body = client.post(f"{_BASE}/{sid}/steps", json=step).json()
    assert len(body["steps"]) == 1
    assert body["steps"][0]["stepId"] == "step-1-dse"
    assert body["steps"][0]["layer"] == "DSE"
    assert body["steps"][0]["lineageEventId"] is None


def test_finish_sets_finished_at_and_notes() -> None:
    client = _client()
    sid = _create(client)["id"]
    body = client.post(f"{_BASE}/{sid}/finish", json={"notes": "partner liked it"}).json()
    assert body["finishedAt"] is not None
    assert body["notes"] == "partner liked it"


def test_list_with_limit_and_offset() -> None:
    client = _client()
    ids = [_create(client, title=f"s{i}")["id"] for i in range(3)]
    full = client.get(_BASE, params={"limit": 50, "offset": 0}).json()["sessions"]
    assert {s["id"] for s in full} >= set(ids)
    page = client.get(_BASE, params={"limit": 1, "offset": 1}).json()["sessions"]
    assert len(page) == 1


def test_get_session_returns_same_summary() -> None:
    client = _client()
    created = _create(client)
    fetched = client.get(f"{_BASE}/{created['id']}").json()
    assert fetched["id"] == created["id"] and fetched["title"] == created["title"]


def test_unknown_session_is_404() -> None:
    client = _client()
    assert client.get(f"{_BASE}/nope").status_code == 404
    assert client.post(f"{_BASE}/nope/steps", json={"layer": "DSE"}).status_code == 404
    assert client.post(f"{_BASE}/nope/finish", json={}).status_code == 404


def test_not_on_external_v1_facade() -> None:
    client = _client(Settings(dse_baas_sandbox_enabled=True))
    assert client.post("/v1/sandbox/sessions", json={"title": "x"}).status_code == 404
    assert client.post(_BASE, json={"title": "x"}).status_code == 200


def test_no_network_or_keys_in_session_flow() -> None:
    client = _client()
    sid = _create(client)["id"]
    client.post(f"{_BASE}/{sid}/steps", json={"layer": "EXECUTION_PREVIEW"})
    blob = str(client.get(f"{_BASE}/{sid}").json())
    for tok in ("apiKey", "privateKey", "ownerAddress", "secret", "signature"):
        assert tok not in blob


def test_header_links_lineage_event_to_session() -> None:
    client = _client()
    sid = _create(client)["id"]
    # An advisory request carrying the session header attaches its lineage event.
    resp = client.post(
        "/api/v1/dss/recommend",
        json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"},
        headers={SANDBOX_SESSION_HEADER: sid},
    )
    assert resp.status_code == 200
    steps = client.get(f"{_BASE}/{sid}").json()["steps"]
    assert len(steps) == 1
    assert steps[0]["layer"] == "DSE"
    assert steps[0]["lineageEventId"]  # the G1L event id was linked


def test_no_header_means_no_auto_session_step() -> None:
    client = _client()
    sid = _create(client)["id"]
    # Same advisory call WITHOUT the header must not touch the session.
    client.post("/api/v1/dss/recommend", json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"})
    assert client.get(f"{_BASE}/{sid}").json()["steps"] == []
