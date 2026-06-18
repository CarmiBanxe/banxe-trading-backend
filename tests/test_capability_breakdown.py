"""M1.22 — capability breakdown (flatten account capabilities, read-only derived, mock-safe).

characterization: by_capability == flatten over account_metadata().accounts[*].capabilities;
total_accounts == len(accounts); total_memberships == sum(counts); EXPLICIT flatten semantics
(multi-capability -> N buckets, empty -> none, total_memberships != total_accounts); deterministic
order + endpoint 200; contract: /accounts/metadata + frozen DTOs unchanged, supported_assets not
surfaced, balances/postings absent; fail-closed: empty-capability -> no bucket, no fabricated key.
"""
from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from banxe_trading_backend.accounts.metadata import (
    AccountAdvisoryMetadata,
    AccountMetadataResponse,
    account_metadata,
)
from banxe_trading_backend.app import create_app
from banxe_trading_backend.meta.breakdown import (
    CapabilityBreakdown,
    CapabilityCount,
    capability_breakdown,
)


def _accts() -> list[AccountAdvisoryMetadata]:
    return account_metadata().accounts


def _flat_expected() -> Counter[str]:
    c: Counter[str] = Counter()
    for a in _accts():
        c.update(a.capabilities)
    return c


def test_counts_match_flatten_group_by() -> None:
    cb = capability_breakdown()
    assert isinstance(cb, CapabilityBreakdown)
    assert {e.capability: e.count for e in cb.by_capability} == dict(_flat_expected())
    assert all(isinstance(e, CapabilityCount) for e in cb.by_capability)


def test_totals_and_flatten_semantics() -> None:
    cb = capability_breakdown()
    accts = _accts()
    assert cb.total_accounts == len(accts)
    assert cb.total_memberships == sum(e.count for e in cb.by_capability)
    assert cb.total_memberships == sum(len(a.capabilities) for a in accts)
    # EXPLICIT flatten semantics: mock accounts have multi-capability -> memberships != accounts
    multi = sum(len(a.capabilities) for a in accts)
    if multi != len(accts):
        assert cb.total_memberships != cb.total_accounts
    assert cb.source == "sandbox-mock"


def test_empty_capability_no_bucket_no_fabrication() -> None:
    cb = capability_breakdown()
    keys = {e.capability for e in cb.by_capability}
    assert "" not in keys and "unknown" not in keys and "none" not in keys
    assert all(e.count > 0 for e in cb.by_capability)
    assert keys == set(_flat_expected())  # only real capabilities


def test_deterministic_sorted_order() -> None:
    cb = capability_breakdown()
    keys = [e.capability for e in cb.by_capability]
    assert keys == sorted(keys)
    assert cb == capability_breakdown()


def test_endpoint_200_shape() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/capability-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"byCapability", "totalAccounts", "totalMemberships", "source"}
    assert body["totalMemberships"] == sum(e["count"] for e in body["byCapability"])
    # supported_assets NOT surfaced; balances/postings absent
    assert "supportedAssets" not in body and "supported_assets" not in r.text
    txt = r.text.lower()
    assert "balance" not in txt and "posting" not in txt and "amount" not in txt


def test_frozen_and_existing_endpoints_unchanged() -> None:
    assert set(AccountAdvisoryMetadata.model_fields.keys()) == {
        "account_type", "ledger_nature", "account_status",
        "supported_assets", "capabilities", "source",
    }
    amr = set(AccountMetadataResponse.model_fields.keys())
    assert amr == {"accounts", "source", "disclaimer"}
    client = TestClient(create_app())
    for p in (
        "/api/v1/accounts/metadata", "/api/v1/catalogue/meta",
        "/api/v1/catalogue/accounts-breakdown", "/api/v1/catalogue/network-breakdown",
    ):
        assert client.get(p).status_code == 200
