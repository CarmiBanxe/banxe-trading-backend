"""M1.18 — instruments breakdown (by fee-schedule / tick-size, read-only derived, mock-safe).

characterization: by_fee_schedule/by_tick_size == group-by over list_instruments; total==len==
sum(by_fee)==sum(by_tick); deterministic order + endpoint 200; contract: frozen DTOs + existing
endpoints unchanged (incl. /instruments/{symbol} not shadowed); fail-closed: no fabricated keys.
"""
from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.instruments.params import list_instruments
from banxe_trading_backend.meta.breakdown import (
    CatalogueBreakdown,
    InstrumentDimensionCount,
    InstrumentsBreakdown,
    MarketsBreakdown,
    instruments_breakdown,
)
from banxe_trading_backend.models import InstrumentInfo


def _ins() -> list[InstrumentInfo]:
    return list_instruments()


def test_counts_match_group_by() -> None:
    ib = instruments_breakdown()
    assert isinstance(ib, InstrumentsBreakdown)
    exp_fee = Counter(i.fee_schedule_ref for i in _ins())
    exp_tick = Counter(i.tick_size for i in _ins())
    assert {e.key: e.count for e in ib.by_fee_schedule} == dict(exp_fee)
    assert {e.key: e.count for e in ib.by_tick_size} == dict(exp_tick)
    all_e = ib.by_fee_schedule + ib.by_tick_size
    assert all(isinstance(e, InstrumentDimensionCount) for e in all_e)


def test_total_and_sum_consistency() -> None:
    ib = instruments_breakdown()
    n = len(_ins())
    assert ib.total == n
    assert sum(e.count for e in ib.by_fee_schedule) == n
    assert sum(e.count for e in ib.by_tick_size) == n
    assert ib.source == "sandbox-mock"


def test_deterministic_sorted_order() -> None:
    ib = instruments_breakdown()
    assert [e.key for e in ib.by_fee_schedule] == sorted(e.key for e in ib.by_fee_schedule)
    assert [e.key for e in ib.by_tick_size] == sorted(e.key for e in ib.by_tick_size)
    assert ib == instruments_breakdown()


def test_no_fabricated_keys() -> None:
    ib = instruments_breakdown()
    assert {e.key for e in ib.by_fee_schedule} == {i.fee_schedule_ref for i in _ins()}
    assert {e.key for e in ib.by_tick_size} == {i.tick_size for i in _ins()}
    assert all(e.count > 0 for e in ib.by_fee_schedule + ib.by_tick_size)


def test_endpoint_200_shape() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/instruments-breakdown")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"byFeeSchedule", "byTickSize", "total", "source"}
    assert body["total"] == sum(e["count"] for e in body["byFeeSchedule"])
    assert "balance" not in r.text.lower() and "apy" not in r.text.lower()


def test_instruments_param_route_not_shadowed() -> None:
    client = TestClient(create_app())
    # the distinct /catalogue/* path must not shadow the /instruments/{symbol} param route
    assert client.get("/api/v1/instruments/BTC-EUR").status_code == 200
    assert client.get("/api/v1/instruments").status_code == 200


def test_frozen_and_existing_endpoints_unchanged() -> None:
    assert set(InstrumentInfo.model_fields.keys()) == {
        "symbol", "tick_size", "min_qty", "max_qty", "fee_schedule_ref",
    }
    assert len(CatalogueBreakdown.model_fields) == 3
    assert len(MarketsBreakdown.model_fields) == 4
    client = TestClient(create_app())
    for p in (
        "/api/v1/catalogue/meta", "/api/v1/catalogue/breakdown", "/api/v1/markets/breakdown",
        "/api/v1/symbols", "/api/v1/earn/taxonomy",
    ):
        assert client.get(p).status_code == 200
