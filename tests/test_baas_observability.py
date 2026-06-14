"""DSE BaaS observability & readiness (T8.2) — internal-only, advisory/mock.

No network. Covers metrics recording + Prometheus exposition, the structured log
(sanitized, no secrets/PII), the internal health/readiness endpoint, and that the
internal endpoints are excluded from the public OpenAPI and add no public fields.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.observability import BaasMetrics, dse_baas_health

_BODY = {"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced"}


def _client(**flags: bool) -> TestClient:
    return TestClient(create_app(Settings(**flags)))


# --------------------------------- metrics ---------------------------------- #


def test_metrics_record_requests_latency_and_top_action() -> None:
    client = _client(dse_baas_sandbox_enabled=True)
    client.post("/v1/dss/recommend", json=_BODY)
    client.post("/v1/dss/recommend", json={"asset": "ETHUSDT", "portfolioValueUsd": "5000"})
    text = client.get("/internal/metrics/dse-baas").text
    assert 'dse_baas_requests_total{asset="BTCUSDT",risk_profile="balanced",status="200"} 1' in text
    assert "dse_baas_request_latency_ms_sum{" in text
    assert "dse_baas_top_action_total{" in text
    assert "dse_baas_debug_requests_total 0" in text


def test_metrics_count_503_when_sandbox_disabled() -> None:
    client = _client()  # flag off
    assert client.post("/v1/dss/recommend", json=_BODY).status_code == 503
    text = client.get("/internal/metrics/dse-baas").text
    assert 'status="503"' in text


def test_metrics_count_debug_requests() -> None:
    client = _client(dse_baas_sandbox_enabled=True, dse_debug_enabled=True)
    client.post("/v1/dss/recommend", json=_BODY, headers={"X-Banxe-Dse-Debug": "true"})
    assert "dse_baas_debug_requests_total 1" in client.get("/internal/metrics/dse-baas").text


def test_metrics_prometheus_escapes_label_values() -> None:
    m = BaasMetrics()
    m.observe(asset='BT"C', risk_profile="balanced", status=200, latency_ms=1.0)
    assert 'asset="BT\\"C"' in m.render_prometheus()


# ------------------------------ structured log ------------------------------ #


def test_structured_log_is_sanitized_json(caplog) -> None:
    client = _client(dse_baas_sandbox_enabled=True)
    with caplog.at_level(logging.INFO, logger="banxe.dse.baas"):
        client.post(
            "/v1/dss/recommend",
            json={
                "asset": "BTCUSDT",
                "portfolioValueUsd": "123456",  # sensitive amount — must NOT be logged
                "riskProfile": "balanced",
                "currentPositions": [{"asset": "BTCUSDT", "sizeUsd": "99999", "side": "long"}],
            },
        )
    line = next(r.getMessage() for r in caplog.records if r.name == "banxe.dse.baas")
    event = json.loads(line)
    # Useful correlation/summary fields are present...
    assert event["event"] == "dse_baas_recommend"
    assert event["asset"] == "BTCUSDT"
    assert event["traceId"].startswith("dss-")
    assert "topActionType" in event and "topDriver" in event
    # ...and no amounts / positions / secrets leak into the log.
    blob = line.lower()
    for forbidden in ("123456", "99999", "portfoliovalue", "positions", "sizeusd", "secret", "key"):
        assert forbidden not in blob


# ----------------------------- health / readiness --------------------------- #


def test_health_ok_when_sandbox_enabled() -> None:
    resp = _client(dse_baas_sandbox_enabled=True).get("/internal/health/dse-baas")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "OK"
    assert body["checks"]["sandboxEnabled"] is True
    assert body["checks"]["dryRun"] == "ok"


def test_health_degraded_when_sandbox_disabled() -> None:
    resp = _client().get("/internal/health/dse-baas")
    assert resp.status_code == 200  # component alive, facade gated off
    body = resp.json()
    assert body["status"] == "DEGRADED"
    assert body["checks"]["sandboxEnabled"] is False


def test_health_error_status_maps_to_503() -> None:
    # A broken engine dry-run → ERROR → 503 (readiness fail).
    class _BrokenEngine:
        async def recommend(self, request, *, debug: bool = False):  # noqa: ARG002
            raise RuntimeError("boom")

    result = asyncio.run(dse_baas_health(sandbox_enabled=True, engine=_BrokenEngine()))
    assert result["status"] == "ERROR"
    assert result["checks"]["dryRun"] == "error"


# --------------------- internal endpoints stay internal --------------------- #


def test_internal_endpoints_excluded_from_openapi() -> None:
    client = _client(dse_baas_sandbox_enabled=True)
    paths = client.get("/openapi.json").json()["paths"]
    assert not any(p.startswith("/internal/") for p in paths)
    # The public BaaS facade is still its normal advisory contract (unchanged).
    body = client.post("/v1/dss/recommend", json=_BODY).json()
    assert "recommendations" in body and "decisionTrace" in body
