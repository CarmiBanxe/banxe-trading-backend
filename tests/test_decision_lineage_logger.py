"""Decision-lineage / audit logging scaffold (G1L) — internal, mock-safe.

No network. Covers: event creation + write to a sink; fail-closed (a raising sink
never breaks the flow); no-op when disabled; defensive redaction; and that each of
the five advisory endpoints triggers exactly one capture with the right layer,
without changing the response contract.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.services.decision_lineage import (
    DecisionLineageEvent,
    DecisionLineageLogger,
    LineageLayer,
    _redact,
    _to_payload,
    build_decision_lineage_logger,
)


class _SpySink:
    def __init__(self) -> None:
        self.events: list[DecisionLineageEvent] = []

    def write(self, event: DecisionLineageEvent) -> None:
        self.events.append(event)


class _BoomSink:
    def write(self, event: DecisionLineageEvent) -> None:  # noqa: ARG002
        raise RuntimeError("storage unavailable")


# ------------------------------- unit: logger ------------------------------- #


def test_record_writes_event_with_defaults() -> None:
    sink = _SpySink()
    logger = DecisionLineageLogger(sink)
    corr = logger.record(
        layer="DSE", request_payload={"asset": "BTC"}, response_payload={"ok": True}
    )
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.layer == "DSE" and ev.id and ev.correlation_id == corr
    assert ev.provider_versions == {"DSE": "mock-2026-06-15"}  # per-layer default
    assert ev.timestamp.tzinfo is not None  # tz-aware (UTC)


def test_failing_sink_is_fail_closed() -> None:
    logger = DecisionLineageLogger(_BoomSink())
    # Must NOT raise — audit failure cannot affect business flow.
    logger.record(layer="FEE_PREVIEW", request_payload={}, response_payload={})


def test_disabled_logger_is_noop() -> None:
    sink = _SpySink()
    logger = DecisionLineageLogger(sink, enabled=False)
    assert logger.enabled is False
    corr = logger.record(
        layer="QUANT_PREVIEW", request_payload={"a": 1}, response_payload={}, correlation_id="x"
    )
    assert sink.events == [] and corr == "x"


def test_build_logger_honours_flag() -> None:
    assert build_decision_lineage_logger(Settings(decision_lineage_enabled=False)).enabled is False
    assert build_decision_lineage_logger(Settings()).enabled is True


def test_redaction_drops_sensitive_keys() -> None:
    raw: dict[str, Any] = {
        "asset": "BTC",
        "apiKey": "should-go",
        "nested": {"secret": "x", "keep": 1, "ownerAddress": "0xabc"},
        "list": [{"token": "t", "ok": 2}],
    }
    out = _redact(raw)
    assert out == {"asset": "BTC", "nested": {"keep": 1}, "list": [{"ok": 2}]}


def test_to_payload_serialises_and_redacts_pydantic() -> None:
    body = {"asset": "ETH", "password": "p"}
    assert _to_payload(body) == {"asset": "ETH"}
    assert _to_payload(None) == {}


# --------------------- integration: endpoints capture once ------------------ #

_ADVISORY_CALLS: list[tuple[str, str, dict[str, Any]]] = [
    ("DSE", "/api/v1/dss/recommend", {"asset": "BTCUSDT", "portfolioValueUsd": "10000"}),
    ("MM_PREVIEW", "/api/v1/mm/preview", {"asset": "BTCUSDT", "spreadBps": 10, "levels": 2}),
    (
        "FEE_PREVIEW",
        "/api/v1/fees/preview",
        {"venue": "x", "productType": "spot", "asset": "ETH", "notionalUsd": "1000"},
    ),
    (
        "QUANT_PREVIEW",
        "/api/v1/quant/preview",
        {"asset": "ETH", "productType": "perp", "notionalUsd": "1000", "horizonDays": 7},
    ),
    (
        "EXECUTION_PREVIEW",
        "/api/v1/execution/intent-preview",
        {"asset": "ETH", "notionalUsd": "1000", "productType": "spot"},
    ),
]


def _spy_app() -> tuple[TestClient, _SpySink]:
    app = create_app()
    sink = _SpySink()
    app.state.decision_lineage_logger = DecisionLineageLogger(sink)
    return TestClient(app), sink


@pytest.mark.parametrize(("layer", "url", "payload"), _ADVISORY_CALLS)
def test_endpoint_emits_one_lineage_event(layer: str, url: str, payload: dict[str, Any]) -> None:
    client, sink = _spy_app()
    resp = client.post(url, json=payload)
    assert resp.status_code == 200
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.layer == layer
    assert ev.correlation_id  # generated when absent on the request
    assert ev.request_payload and ev.response_payload  # both captured


def test_failing_logger_does_not_break_endpoint() -> None:
    app = create_app()
    app.state.decision_lineage_logger = DecisionLineageLogger(_BoomSink())
    client = TestClient(app)
    resp = client.post("/api/v1/quant/preview", json=_ADVISORY_CALLS[3][2])
    assert resp.status_code == 200  # business flow unaffected by audit failure


def test_disabled_logger_captures_nothing_but_serves() -> None:
    app = create_app(Settings(decision_lineage_enabled=False))
    sink = _SpySink()
    # Even if a sink is attached, a disabled logger writes nothing.
    app.state.decision_lineage_logger = DecisionLineageLogger(sink, enabled=False)
    client = TestClient(app)
    resp = client.post("/api/v1/fees/preview", json=_ADVISORY_CALLS[2][2])
    assert resp.status_code == 200 and sink.events == []


def test_missing_logger_state_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    # record_lineage must be a no-op (not an error) if app.state has no logger.
    app = create_app()
    if hasattr(app.state, "decision_lineage_logger"):
        delattr(app.state, "decision_lineage_logger")
    client = TestClient(app)
    resp = client.post("/api/v1/mm/preview", json=_ADVISORY_CALLS[1][2])
    assert resp.status_code == 200


def test_partner_id_captured_from_existing_dse_context() -> None:
    client, sink = _spy_app()
    body = {
        "asset": "BTCUSDT",
        "portfolioValueUsd": "10000",
        "partnerContext": {"mode": "sandbox", "partnerId": "acme"},
    }
    resp = client.post("/api/v1/dss/recommend", json=body)
    assert resp.status_code == 200
    assert sink.events[0].partner_id == "acme"  # reused existing id, no new field


def test_all_layers_have_a_default_provider_version() -> None:
    sink = _SpySink()
    logger = DecisionLineageLogger(sink)
    layers: list[LineageLayer] = [
        "DSE",
        "MM_PREVIEW",
        "FEE_PREVIEW",
        "QUANT_PREVIEW",
        "EXECUTION_PREVIEW",
    ]
    for layer in layers:
        logger.record(layer=layer, request_payload={}, response_payload={})
    assert all(ev.provider_versions for ev in sink.events)
    assert len(sink.events) == len(layers)
