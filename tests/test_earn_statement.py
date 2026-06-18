"""M1.6 — earn advisory read-only statement/summary (additive, advisory, mock-safe).

characterization: statement composed from existing advisory sources; contract: EarnMetrics /
EarnRatesResponse / AnalyticsContext frozen and /earn/rates unchanged; negative: fail-closed
(skip / empty, never a fake value) when an upstream advisory source raises.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.dse.models import AnalyticsContext, EarnMetrics
from banxe_trading_backend.earn import (
    EarnAdvisoryStatus,
    EarnStatement,
    EarnStatementResponse,
    MockEarnRatesCatalog,
    MockEarnRatesProvider,
    earn_statement,
)
from banxe_trading_backend.earn.rates import EarnRatesResponse

_NOW = "2026-06-18T00:00:00+00:00"


def _catalog() -> MockEarnRatesCatalog:
    return MockEarnRatesCatalog(MockEarnRatesProvider())


# ---- characterization: statement composed from existing advisory sources ---------

def test_statement_composed_for_basket() -> None:
    resp = asyncio.run(
        earn_statement(_catalog(), MockEarnRatesProvider(), assets=["BTC", "ETH", "USDC"], now=_NOW)
    )
    assert isinstance(resp, EarnStatementResponse)
    assert resp.source == "sandbox-mock"
    assert resp.statements
    for st in resp.statements:
        assert isinstance(st, EarnStatement)
        assert st.asset and st.protocol and st.fee_summary
        Decimal(st.current_yield_pct)  # DecimalStr / I-01 parseable
        assert st.risk_band in {"low", "medium", "high"}
        assert st.advisory_status == EarnAdvisoryStatus.NORMAL.value
        assert st.source == "sandbox-mock"


def test_statement_defaults_to_basket_when_no_assets() -> None:
    resp = asyncio.run(earn_statement(_catalog(), MockEarnRatesProvider(), assets=[], now=_NOW))
    assert resp.statements  # default basket used


def test_statement_endpoint_read_only_200() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/earn/statement")
    assert r.status_code == 200
    body = r.json()
    assert body["statements"]
    assert body["statements"][0]["advisoryStatus"] == "NORMAL"
    assert body["source"] == "sandbox-mock"


# ---- contract: frozen consumers + /earn/rates unchanged --------------------------

def test_frozen_contracts_unchanged() -> None:
    assert set(EarnMetrics.model_fields.keys()) == {
        "current_yield_pct", "protocol", "chain", "lockup_days", "variable_rate", "risk_summary",
    }
    assert set(EarnRatesResponse.model_fields.keys()) == {"rates", "source", "as_of", "disclaimer"}
    assert set(AnalyticsContext.model_fields.keys()) == {
        "greeks_summary", "earn_alternatives", "analytics_version", "source",
    }


def test_existing_rates_endpoint_unchanged() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/earn/rates")
    assert r.status_code == 200
    assert "rates" in r.json()  # existing /earn/rates surface intact


# ---- negative / fail-closed ------------------------------------------------------

class _RaisingProvider:
    async def get_earn_metrics(self, asset: str) -> EarnMetrics:  # noqa: ARG002
        raise RuntimeError("advisory detail unavailable")


def test_statement_fail_closed_skips_when_detail_unavailable() -> None:
    # cards exist (catalog) but the detail provider raises -> every asset skipped, no fake value
    resp = asyncio.run(
        earn_statement(_catalog(), _RaisingProvider(), assets=["BTC", "ETH"], now=_NOW)
    )
    assert resp.statements == []
    assert resp.source == "sandbox-mock"  # response still consistent/advisory
