"""M1.15 — earn taxonomy reference surface (read-only descriptors, mock-safe).

characterization: enumerates expected risk bands / statuses / tenor buckets with correct ordering
and config labels; contract: frozen earn DTOs/enums + existing endpoints unchanged; negative/
fail-closed: live-pipeline txn states absent from taxonomy; full enum coverage; no fabrication.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.dse.models import AnalyticsContext, EarnMetrics
from banxe_trading_backend.earn.rates import EarnRatesResponse, RateCard, RiskBand
from banxe_trading_backend.earn.statement import EarnStatement
from banxe_trading_backend.earn.status import EarnAdvisoryStatus, from_legacy
from banxe_trading_backend.earn.taxonomy import (
    EarnTaxonomy,
    earn_taxonomy,
)

_LIVE_PIPELINE = {
    "DRAFT", "FIAT_SENDING", "EXCHANGING", "FEE_SENDING", "MAIN_SENDING",
    "CRYPTO_EARN_SENDING", "WITHDRAW_TRANSACTION_AWAITING",
}


def test_risk_bands_enumerated_ordered() -> None:
    tx = earn_taxonomy()
    assert isinstance(tx, EarnTaxonomy)
    codes = [b.code for b in tx.risk_bands]
    assert codes == ["low", "medium", "high"]  # ordered low<medium<high
    assert [b.ordering for b in tx.risk_bands] == [1, 2, 3]
    assert {b.code for b in tx.risk_bands} == {b.value for b in RiskBand}  # derived from enum


def test_statuses_full_enum_coverage() -> None:
    tx = earn_taxonomy()
    codes = {s.code for s in tx.advisory_statuses}
    assert codes == {s.value for s in EarnAdvisoryStatus}  # all 11, derived from enum
    assert all(s.phase in {"active", "terminal", "inactive", "error"} for s in tx.advisory_statuses)


def test_lockup_tenor_buckets() -> None:
    tx = earn_taxonomy()
    codes = [t.code for t in tx.lockup_tenors]
    assert codes == ["flexible", "short", "medium", "locked"]
    assert tx.lockup_tenors[0].min_days == 0 and tx.lockup_tenors[-1].max_days is None


def test_endpoint_200_shape() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/earn/taxonomy")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"riskBands", "advisoryStatuses", "lockupTenors", "source"}
    assert body["source"] == "sandbox-mock"
    # key set is exactly the reference fields -> no apy/balance/amount fields leak
    for entry in body["riskBands"] + body["advisoryStatuses"] + body["lockupTenors"]:
        assert not (set(entry) & {"apy", "apyPct", "balance", "amount", "price"})


def test_no_live_pipeline_states_in_taxonomy() -> None:
    tx = earn_taxonomy()
    codes = {s.code for s in tx.advisory_statuses}
    assert not (codes & _LIVE_PIPELINE)  # operator-gated live states never surfaced
    for live in _LIVE_PIPELINE:
        with pytest.raises(ValueError):
            from_legacy(live)  # status SoT still fail-closes on live states


def test_frozen_contracts_unchanged() -> None:
    assert [b.value for b in RiskBand] == ["low", "medium", "high"]
    assert len(list(EarnAdvisoryStatus)) == 11
    assert len(EarnMetrics.model_fields) == 6
    assert set(EarnRatesResponse.model_fields.keys()) == {"rates", "source", "as_of", "disclaimer"}
    assert set(AnalyticsContext.model_fields.keys()) == {
        "greeks_summary", "earn_alternatives", "analytics_version", "source",
    }
    assert set(RateCard.model_fields.keys()) == {
        "asset", "protocol", "apy_pct", "lockup_days", "variable_rate", "risk_band", "source",
    }
    assert "current_yield_pct" in EarnStatement.model_fields


def test_existing_earn_endpoints_unchanged() -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/earn/rates").status_code == 200
    assert client.get("/api/v1/earn/statement").status_code == 200
