"""DSE BaaS sandbox facade (T8.1) — external advisory endpoint, flag-gated.

No network, mock-only. Covers the sandbox flag gate (503 when off), the thin
facade (same engine / same output as the internal endpoint), advisory-only
behaviour, the decisionTrace double-gate through the facade, and that the
internal terminal endpoint is unaffected.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings

_BODY = {"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced"}

_BAAS = "/v1/dss/recommend"
_INTERNAL = "/api/v1/dss/recommend"


def _client(**flags: bool) -> TestClient:
    return TestClient(create_app(Settings(**flags)))


# ------------------------------- sandbox gate ------------------------------- #


def test_facade_disabled_by_default_returns_503() -> None:
    resp = _client().post(_BAAS, json=_BODY)
    assert resp.status_code == 503
    assert "sandbox" in resp.json()["detail"].lower()


def test_facade_disabled_for_every_request() -> None:
    client = _client()  # flag off
    for body in (_BODY, {"asset": "ETHUSDT", "portfolioValueUsd": "5000"}):
        assert client.post(_BAAS, json=body).status_code == 503


def test_facade_enabled_returns_advisory_recommendations() -> None:
    resp = _client(dse_baas_sandbox_enabled=True).post(_BAAS, json=_BODY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendations"] and body["disclaimer"]
    # advisory contract intact (explainability fields from T7.7 present).
    assert body["traceId"].startswith("dss-")
    ranks = [r["rank"] for r in body["recommendations"]]
    assert ranks == list(range(1, len(ranks) + 1))


# --------------------------- thin facade equivalence ------------------------ #


def test_facade_matches_internal_engine_output() -> None:
    client = _client(dse_baas_sandbox_enabled=True)
    facade = client.post(_BAAS, json=_BODY).json()
    internal = client.post(_INTERNAL, json=_BODY).json()
    # Same engine → identical ranking, scores and traceId (utility unchanged).
    assert [r["utilityScore"] for r in facade["recommendations"]] == [
        r["utilityScore"] for r in internal["recommendations"]
    ]
    assert [r["action"]["type"] for r in facade["recommendations"]] == [
        r["action"]["type"] for r in internal["recommendations"]
    ]
    assert facade["traceId"] == internal["traceId"]


def test_internal_endpoint_unaffected_by_sandbox_flag() -> None:
    # The terminal endpoint works whether or not the BaaS sandbox is enabled.
    assert _client().post(_INTERNAL, json=_BODY).status_code == 200
    assert _client(dse_baas_sandbox_enabled=True).post(_INTERNAL, json=_BODY).status_code == 200


# ------------------------------ advisory / validation ----------------------- #


def test_facade_validation_error_is_422() -> None:
    resp = _client(dse_baas_sandbox_enabled=True).post(
        _BAAS, json={"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "custom"}
    )
    assert resp.status_code == 422  # custom profile without customWeights


# --------------------- decisionTrace stays double-gated --------------------- #


def test_facade_decision_trace_requires_both_gates() -> None:
    # Sandbox on, debug off → no trace even with the header.
    no_debug = _client(dse_baas_sandbox_enabled=True)
    r1 = no_debug.post(_BAAS, json=_BODY, headers={"X-Banxe-Dse-Debug": "true"})
    assert r1.json()["decisionTrace"] is None
    # Sandbox on + debug on + header → trace present (routes into the engine).
    both = _client(dse_baas_sandbox_enabled=True, dse_debug_enabled=True)
    r2 = both.post(_BAAS, json=_BODY, headers={"X-Banxe-Dse-Debug": "true"})
    body = r2.json()
    assert body["decisionTrace"]["traceId"] == body["traceId"]
    # ...and still off without the header.
    r3 = both.post(_BAAS, json=_BODY)
    assert r3.json()["decisionTrace"] is None
