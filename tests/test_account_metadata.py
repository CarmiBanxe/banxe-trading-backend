"""M1.7 — advisory account metadata (additive, read-only, config-as-data, mock-safe).

characterization: metadata assembly + endpoint 200; contract: existing endpoints/contracts
(earn rates/statement, EarnMetrics/AnalyticsContext/EarnRatesResponse, WalletAuthPort) unchanged;
negative: fail-closed (skip malformed/unsupported config; never a fake value).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.accounts.metadata import (
    AccountAdvisoryMetadata,
    AccountMetadataResponse,
    account_metadata,
)
from banxe_trading_backend.app import create_app
from banxe_trading_backend.dse.models import AnalyticsContext, EarnMetrics
from banxe_trading_backend.earn.rates import EarnRatesResponse
from banxe_trading_backend.ports.wallet_auth_port import WalletAuthPort

_TYPES = {"INTERNAL", "EXTERNAL", "SYSTEM"}
_NATURES = {"ACTIVE", "PASSIVE"}
_STATUSES = {"ACTIVE", "CLOSED", "CLOSING"}


# ---- characterization ------------------------------------------------------------

def test_account_metadata_assembled() -> None:
    resp = account_metadata()
    assert isinstance(resp, AccountMetadataResponse)
    assert resp.source == "sandbox-mock"
    assert resp.accounts
    for a in resp.accounts:
        assert isinstance(a, AccountAdvisoryMetadata)
        assert a.account_type in _TYPES
        assert a.ledger_nature in _NATURES
        assert a.account_status in _STATUSES
        assert isinstance(a.supported_assets, list)
        assert isinstance(a.capabilities, list)
        assert a.source == "sandbox-mock"


def test_account_metadata_endpoint_200() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/accounts/metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["accounts"]
    assert body["accounts"][0]["accountType"] in _TYPES
    assert body["source"] == "sandbox-mock"
    # advisory only: no balance/amount/posting FIELDS in account objects
    acct_keys = set(body["accounts"][0].keys())
    assert not (acct_keys & {"balance", "balances", "amount", "posting", "postings"})


# ---- contract: existing surfaces unchanged --------------------------------------

def test_existing_contracts_and_endpoints_unchanged() -> None:
    assert set(EarnMetrics.model_fields.keys()) == {
        "current_yield_pct", "protocol", "chain", "lockup_days", "variable_rate", "risk_summary",
    }
    assert set(EarnRatesResponse.model_fields.keys()) == {"rates", "source", "as_of", "disclaimer"}
    assert set(AnalyticsContext.model_fields.keys()) == {
        "greeks_summary", "earn_alternatives", "analytics_version", "source",
    }
    client = TestClient(create_app())
    assert client.get("/api/v1/earn/rates").status_code == 200
    assert client.get("/api/v1/earn/statement").status_code == 200


def test_wallet_auth_port_untouched() -> None:
    # auth is a separate concern; the SIWE port surface is unchanged
    for m in ("issue_nonce", "verify", "validate_token"):
        assert hasattr(WalletAuthPort, m)


# ---- negative / fail-closed ------------------------------------------------------

def test_fail_closed_skips_malformed_config() -> None:
    bad = (
        {"account_type": "BOGUS", "ledger_nature": "ACTIVE", "account_status": "ACTIVE"},
        {"account_type": "INTERNAL", "ledger_nature": "WRONG", "account_status": "ACTIVE"},
        {"account_type": "INTERNAL", "ledger_nature": "ACTIVE", "account_status": "ACTIVE",
         "supported_assets": ["EUR"], "capabilities": ["fiat"]},  # the only valid one
    )
    resp = account_metadata(config=bad)
    assert len(resp.accounts) == 1
    assert resp.accounts[0].account_type == "INTERNAL"


def test_fail_closed_empty_config_consistent() -> None:
    resp = account_metadata(config=())
    assert resp.accounts == []
    assert resp.source == "sandbox-mock"
