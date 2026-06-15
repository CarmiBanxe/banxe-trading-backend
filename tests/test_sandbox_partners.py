"""Partner sandbox pack (SBOX-4) — internal, mock-safe, demo-only.

No network. Covers: the list (≥3 profiles, no empty fields), detail by id and slug,
unknown-id 404, the demo bundle (profile + scenarios + how-to, no secrets), no
KYB/billing/tier-activation fields, not-on-/v1, and determinism.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings

_BASE = "/api/v1/sandbox/partners"


def _client(settings: Settings | None = None) -> TestClient:
    return TestClient(create_app(settings))


def test_list_returns_at_least_three_profiles() -> None:
    body = _client().get(_BASE).json()
    partners = body["partners"]
    assert len(partners) >= 3
    slugs = {p["slug"] for p in partners}
    assert {"foobank-neo", "walletco-demo", "brokerx-sandbox"} <= slugs
    for p in partners:
        assert p["id"] and p["slug"] and p["name"] and p["segment"]
        assert p["region"] and p["useCase"] and p["enabledModules"]
        assert p["sampleRateLimitTier"].startswith("sandbox-")


def test_detail_by_id_and_slug() -> None:
    client = _client()
    by_slug = client.get(f"{_BASE}/foobank-neo")
    assert by_slug.status_code == 200
    pid = by_slug.json()["id"]
    by_id = client.get(f"{_BASE}/{pid}")
    assert by_id.status_code == 200 and by_id.json()["slug"] == "foobank-neo"


def test_unknown_partner_is_404() -> None:
    assert _client().get(f"{_BASE}/nope").status_code == 404
    assert _client().get(f"{_BASE}/nope/bundle").status_code == 404


def test_bundle_has_profile_scenarios_and_no_secrets() -> None:
    client = _client()
    bundle = client.get(f"{_BASE}/walletco-demo/bundle").json()
    assert bundle["partner"]["slug"] == "walletco-demo"
    assert len(bundle["recommendedScenarios"]) >= 3
    assert bundle["sandboxStatusUrl"] == "/api/v1/sandbox/status"
    assert bundle["sessionsUrl"] == "/api/v1/sandbox/sessions"
    assert bundle["disclaimers"]
    blob = str(bundle)
    for tok in ("apiKey", "api_key", "secret", "token", "privateKey", "password"):
        assert tok not in blob


def test_no_kyb_billing_or_tier_activation_fields() -> None:
    # The invariant is structural: a profile exposes only descriptive fields — no
    # KYB / billing / tier-activation / credential FIELD exists. (The disclaimer text
    # may mention those words in negation, so we check keys, not prose.)
    profile = _client().get(f"{_BASE}/foobank-neo").json()
    assert set(profile) == {
        "id", "slug", "name", "segment", "region", "useCase",
        "enabledModules", "sampleRateLimitTier", "disclaimer",
    }


def test_partners_are_deterministic() -> None:
    client = _client()
    assert client.get(_BASE).json() == client.get(_BASE).json()
    assert (
        client.get(f"{_BASE}/brokerx-sandbox/bundle").json()
        == client.get(f"{_BASE}/brokerx-sandbox/bundle").json()
    )


def test_not_on_external_v1_facade() -> None:
    client = _client(Settings(dse_baas_sandbox_enabled=True))
    assert client.get("/v1/sandbox/partners").status_code == 404
    assert client.get(_BASE).status_code == 200
