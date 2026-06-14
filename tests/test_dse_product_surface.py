"""DSE partner/product surface (Sprint S11) — non-breaking, advisory, mock-safe.

No network. Covers backward compatibility (opt-in presence/absence), ranking
stability, safe provenance + no secret leakage, deterministic mock behaviour,
fail-closed unsupported partner modes, and spec ↔ model conformance.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.dse import PartnerContext, ProductMetadata

_SPECS = Path(__file__).resolve().parents[1] / "docs" / "specs"
_BODY = {"asset": "BTCUSDT", "portfolioValueUsd": "10000", "riskProfile": "balanced"}


def _client() -> TestClient:
    return TestClient(create_app())


def _post(body: dict) -> dict:
    return _client().post("/api/v1/dss/recommend", json=body).json()


# --------------------- backward compatibility / opt-in ---------------------- #


def test_product_absent_without_partner_context() -> None:
    # Existing callers (no partnerContext) get product = null — non-breaking.
    body = _post(_BODY)
    assert body["product"] is None


def test_product_present_only_when_opted_in() -> None:
    body = _post({**_BODY, "partnerContext": {"partnerId": "acme-sbx", "clientRef": "r1"}})
    p = body["product"]
    assert p is not None
    assert p["surface"] == "dse-baas-sandbox"
    assert p["engineMode"] == "sandbox-mock"
    assert (p["advisory"], p["executes"], p["selfCustodial"]) == (True, False, True)
    assert p["determinism"] == "deterministic-mock"
    # safe provenance class per domain (mock by default).
    assert p["providerProvenance"] == {"market": "mock", "sentiment": "mock", "stress": "mock"}
    # correlation id == traceId (metering-ready; no billing).
    assert p["requestId"] == body["traceId"]
    # partner context echoed safely (mode defaulted to sandbox).
    assert p["partner"] == {"partnerId": "acme-sbx", "clientRef": "r1", "mode": "sandbox"}
    assert p["explanationModel"].startswith("U_a =")


def test_ranking_unchanged_with_and_without_partner_context() -> None:
    plain = _post(_BODY)
    opted = _post({**_BODY, "partnerContext": {"partnerId": "p"}})
    assert [r["utilityScore"] for r in plain["recommendations"]] == [
        r["utilityScore"] for r in opted["recommendations"]
    ]
    assert [r["action"]["type"] for r in plain["recommendations"]] == [
        r["action"]["type"] for r in opted["recommendations"]
    ]


# ----------------------- provenance reflects the tier ----------------------- #


def test_provenance_reflects_live_ready_as_inert_label() -> None:
    client = TestClient(create_app(Settings(dse_sentiment_tier="live-ready")))
    body = client.post(
        "/api/v1/dss/recommend", json={**_BODY, "partnerContext": {"partnerId": "p"}}
    ).json()
    prov = body["product"]["providerProvenance"]
    assert prov["sentiment"] == "inert-live-ready"
    assert prov["market"] == "mock"


# --------------------------- fail-closed modes ------------------------------ #


def test_non_sandbox_partner_mode_fails_closed() -> None:
    resp = _client().post(
        "/api/v1/dss/recommend",
        json={**_BODY, "partnerContext": {"mode": "production"}},
    )
    assert resp.status_code == 422  # schema-layer fail-closed (request validation)
    assert "OPERATOR DECISION REQUIRED" in json.dumps(resp.json())


def test_malformed_partner_id_is_rejected() -> None:
    # Bounded charset (no secrets/PII/injection) — invalid input is 422.
    bad = _client().post(
        "/api/v1/dss/recommend", json={**_BODY, "partnerContext": {"partnerId": "has space!"}}
    )
    assert bad.status_code == 422
    toolong = _client().post(
        "/api/v1/dss/recommend",
        json={**_BODY, "partnerContext": {"partnerId": "x" * 65}},
    )
    assert toolong.status_code == 422


# ------------------------------ no secret leakage --------------------------- #


def test_product_block_carries_no_secrets() -> None:
    body = _post({**_BODY, "partnerContext": {"partnerId": "acme"}})
    blob = json.dumps(body["product"]).lower()
    for forbidden in ("api_key", "secret", "token", "password", "base_url", "http://", "https://"):
        assert forbidden not in blob


# ----------------------- determinism (mock) --------------------------------- #


def test_product_is_deterministic_in_mock_mode() -> None:
    a = _post({**_BODY, "partnerContext": {"partnerId": "acme", "clientRef": "r"}})
    b = _post({**_BODY, "partnerContext": {"partnerId": "acme", "clientRef": "r"}})
    assert a["product"] == b["product"]
    assert a["product"]["requestId"] == b["product"]["requestId"]


# ----------------------- spec ↔ model conformance --------------------------- #


def _schema_props(schema: str) -> set[str]:
    doc = yaml.safe_load((_SPECS / "dse-baas-api.yaml").read_text())
    return set(doc["components"]["schemas"][schema]["properties"].keys())


def _aliases(model: type) -> set[str]:
    return {fi.alias or name for name, fi in model.model_fields.items()}  # type: ignore[attr-defined]


def test_partner_product_models_match_spec() -> None:
    assert _aliases(PartnerContext) == _schema_props("PartnerContext")
    assert _aliases(ProductMetadata) == _schema_props("ProductMetadata")
