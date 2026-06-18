"""M1.23 — supported-asset breakdown (flatten account supported_assets, read-only, mock-safe).

characterization: by_supported_asset == flatten group-by over account_metadata().accounts[*].
supported_assets; total_accounts==len; total_memberships==sum(counts); EXPLICIT
flatten semantics (multi-asset->N buckets, empty SYSTEM->none, memberships != accounts);
deterministic order + endpoint 200; contract: frozen DTOs + existing endpoints unchanged (asset
catalogue not duplicated); fail-closed: empty -> no bucket, no fabricated key.
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
    SupportedAssetBreakdown,
    SupportedAssetCount,
    supported_asset_breakdown,
)


def _accts() -> list[AccountAdvisoryMetadata]:
    return account_metadata().accounts


def _flat_expected() -> Counter[str]:
    c: Counter[str] = Counter()
    for a in _accts():
        c.update(set(a.supported_assets))  # account counts once per asset
    return c


def test_counts_match_flatten_group_by() -> None:
    sab = supported_asset_breakdown()
    assert isinstance(sab, SupportedAssetBreakdown)
    assert {e.asset: e.count for e in sab.by_supported_asset} == dict(_flat_expected())
    assert all(isinstance(e, SupportedAssetCount) for e in sab.by_supported_asset)


def test_totals_and_flatten_semantics() -> None:
    sab = supported_asset_breakdown()
    accts = _accts()
    assert sab.total_accounts == len(accts)
    assert sab.total_memberships == sum(e.count for e in sab.by_supported_asset)
    assert sab.total_memberships == sum(len(a.supported_assets) for a in accts)
    # EXPLICIT flatten: multi-asset accounts + empty SYSTEM => memberships != accounts
    if sum(len(a.supported_assets) for a in accts) != len(accts):
        assert sab.total_memberships != sab.total_accounts
    assert sab.source == "sandbox-mock"


def test_empty_supported_assets_no_bucket() -> None:
    sab = supported_asset_breakdown()
    keys = {e.asset for e in sab.by_supported_asset}
    assert "" not in keys and "unknown" not in keys and "none" not in keys
    assert all(e.count > 0 for e in sab.by_supported_asset)
    assert keys == set(_flat_expected())  # only real supported assets


def test_deterministic_sorted_order() -> None:
    sab = supported_asset_breakdown()
    keys = [e.asset for e in sab.by_supported_asset]
    assert keys == sorted(keys)
    assert sab == supported_asset_breakdown()


def test_endpoint_200_shape() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/supported-asset-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"bySupportedAsset", "totalAccounts", "totalMemberships", "source"}
    assert body["totalMemberships"] == sum(e["count"] for e in body["bySupportedAsset"])
    txt = r.text.lower()
    assert "balance" not in txt and "posting" not in txt and "amount" not in txt


def test_frozen_and_existing_endpoints_unchanged() -> None:
    amf = set(AccountAdvisoryMetadata.model_fields.keys())
    assert amf == {
        "account_type", "ledger_nature", "account_status",
        "supported_assets", "capabilities", "source",
    }
    amr = set(AccountMetadataResponse.model_fields.keys())
    assert amr == {"accounts", "source", "disclaimer"}
    client = TestClient(create_app())
    for p in (
        "/api/v1/accounts/metadata", "/api/v1/assets/metadata",
        "/api/v1/catalogue/accounts-breakdown", "/api/v1/catalogue/capability-breakdown",
        "/api/v1/catalogue/network-breakdown",
    ):
        assert client.get(p).status_code == 200


def test_count_equals_accounts_containing_asset() -> None:
    # Contract: count == number of ACCOUNTS that support the asset (dedupe per account;
    # a duplicate entry within one account must not double-count). CodeRabbit #56 finding.
    sab = supported_asset_breakdown()
    accts = _accts()
    for e in sab.by_supported_asset:
        containing = sum(1 for a in accts if e.asset in set(a.supported_assets))
        assert e.count == containing
        assert e.count <= sab.total_accounts
