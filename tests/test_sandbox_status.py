"""Unified sandbox-status surface (SBOX-1) — internal, mock-safe.

No network. Covers: 200 OK + expected camelCase flags; deterministic response;
the profile builder; not reachable on the external /v1 facade; and that the
advisory CORE contracts are unchanged alongside it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.services.sandbox_profile import build_sandbox_profile

_URL = "/api/v1/sandbox/status"


def _client(settings: Settings | None = None) -> TestClient:
    return TestClient(create_app(settings))


def test_sandbox_status_ok_and_flags() -> None:
    body = _client().get(_URL).json()
    assert body["mode"] == "sandbox-demo"
    assert body["executionMode"] == "unsigned-preview-only"
    assert body["liveProvidersEnabled"] is False
    assert body["billingEnabled"] is False
    assert body["kybEnabled"] is False
    assert body["lineageEnabled"] is True
    assert "No live trading" in body["disclaimer"]
    assert body["advisoryModules"] == [
        "dss",
        "mm-preview",
        "fees-preview",
        "quant-preview",
        "execution-intent-preview",
        "marketplace",
    ]


def test_sandbox_status_is_deterministic() -> None:
    client = _client()
    assert client.get(_URL).json() == client.get(_URL).json()


def test_lineage_flag_follows_config() -> None:
    body = _client(Settings(decision_lineage_enabled=False)).get(_URL).json()
    assert body["lineageEnabled"] is False


def test_profile_builder_matches_endpoint() -> None:
    profile = build_sandbox_profile(Settings())
    assert profile.mode == "sandbox-demo"
    assert profile.execution_mode == "unsigned-preview-only"
    assert profile.live_providers_enabled is False  # all providers mock in sandbox
    assert profile.billing_enabled is False and profile.kyb_enabled is False


def test_not_on_external_v1_facade() -> None:
    client = _client(Settings(dse_baas_sandbox_enabled=True))
    assert client.get("/v1/sandbox/status").status_code == 404
    assert client.get(_URL).status_code == 200


def test_core_contracts_unchanged_alongside_sandbox() -> None:
    client = _client()
    dss = client.post(
        "/api/v1/dss/recommend", json={"asset": "BTCUSDT", "portfolioValueUsd": "10000"}
    )
    assert dss.status_code == 200
    fees_body = {"venue": "x", "productType": "spot", "asset": "ETH", "notionalUsd": "1000"}
    for url, payload in (
        ("/api/v1/mm/preview", {"asset": "BTCUSDT", "spreadBps": 10, "levels": 2}),
        ("/api/v1/fees/preview", fees_body),
    ):
        assert client.post(url, json=payload).status_code == 200
    assert client.get("/api/v1/marketplace/providers").status_code == 200
