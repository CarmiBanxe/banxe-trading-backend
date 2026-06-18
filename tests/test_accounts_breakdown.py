"""M1.20 — accounts breakdown (by type / ledger-nature / status, read-only derived, mock-safe).

characterization: grouped counts for the 3 categoricals, total==len==each grouped sum, order
order + endpoint 200; contract: /accounts/metadata + frozen DTOs unchanged, balances absent,
list-valued dims not surfaced; fail-closed: no fabricated categories.
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
    AccountDimensionCount,
    AccountsBreakdown,
    accounts_breakdown,
)


def _accts() -> list[AccountAdvisoryMetadata]:
    return account_metadata().accounts


def test_counts_match_group_by() -> None:
    ab = accounts_breakdown()
    assert isinstance(ab, AccountsBreakdown)
    accts = _accts()
    assert {e.key: e.count for e in ab.by_account_type} == dict(
        Counter(a.account_type for a in accts)
    )
    assert {e.key: e.count for e in ab.by_ledger_nature} == dict(
        Counter(a.ledger_nature for a in accts)
    )
    assert {e.key: e.count for e in ab.by_account_status} == dict(
        Counter(a.account_status for a in accts)
    )
    assert all(isinstance(e, AccountDimensionCount) for e in ab.by_account_type)


def test_total_and_sum_consistency_all_dims() -> None:
    ab = accounts_breakdown()
    n = len(_accts())
    assert ab.total == n
    assert sum(e.count for e in ab.by_account_type) == n
    assert sum(e.count for e in ab.by_ledger_nature) == n
    assert sum(e.count for e in ab.by_account_status) == n
    assert ab.source == "sandbox-mock"


def test_deterministic_sorted_order() -> None:
    ab = accounts_breakdown()
    for dim in (ab.by_account_type, ab.by_ledger_nature, ab.by_account_status):
        assert [e.key for e in dim] == sorted(e.key for e in dim)
    assert ab == accounts_breakdown()


def test_no_fabricated_categories() -> None:
    ab = accounts_breakdown()
    assert {e.key for e in ab.by_account_type} == {a.account_type for a in _accts()}
    assert all(e.count > 0 for e in ab.by_account_type + ab.by_ledger_nature + ab.by_account_status)


def test_endpoint_200_shape_no_list_dims_no_balances() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/accounts-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "byAccountType", "byLedgerNature", "byAccountStatus", "total", "source",
    }
    assert body["total"] == sum(e["count"] for e in body["byAccountType"])
    # list-valued dims and balances NOT surfaced
    assert "supportedAssets" not in body and "capabilities" not in body
    txt = r.text.lower()
    assert "balance" not in txt and "posting" not in txt and "amount" not in txt


def test_accounts_metadata_and_frozen_unchanged() -> None:
    assert set(AccountAdvisoryMetadata.model_fields.keys()) == {
        "account_type", "ledger_nature", "account_status",
        "supported_assets", "capabilities", "source",
    }
    assert set(AccountMetadataResponse.model_fields.keys()) == {"accounts", "source", "disclaimer"}
    client = TestClient(create_app())
    for p in (
        "/api/v1/accounts/metadata", "/api/v1/catalogue/meta", "/api/v1/catalogue/breakdown",
        "/api/v1/catalogue/instruments-breakdown", "/api/v1/catalogue/symbols-breakdown",
    ):
        assert client.get(p).status_code == 200
