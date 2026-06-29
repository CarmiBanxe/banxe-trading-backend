"""S6.8 — FE↔BFF mock-loop contract test (wire-not-build).

Asserts the wire contract the FE proxy/WS client (banxe-trading-frontend
``src/shared/api/trade-proxy.ts`` + ``ws-client.ts``) binds against the existing
BFF surface, exercised over the deterministic mock feed (IL-185):

  * WS ``/ws/orderbook/{symbol}`` emits the verbatim §D2 envelope shape
    ``{type, data:{bids, asks, sequence}}`` the FE expects, with decimal-string
    prices/quantities (I-01) and a strictly increasing sequence.
  * REST ``/api/v1/execution/intent-preview`` returns an UNSIGNED intent
    (``signed=False`` and ``submitted=False`` at every level), with a
    decimal-string ``amount``, in mock-default config.
  * In mock-default (``auth_enabled=False``) the FE can call the endpoint with
    NO ``Authorization`` header — proving the backend holds no keys, signs
    nothing, and runs read-only market data + unsigned orders only.

This is contract-assertion only — no production code changes on the backend.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient


def test_ws_orderbook_emits_fe_envelope_shape(client: TestClient) -> None:
    """FE wire: §D2 envelope from /ws/orderbook/{symbol} (mock feed, IL-185)."""
    with client.websocket_connect("/ws/orderbook/BTC-EUR") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        data = snap["data"]
        assert set(data.keys()) >= {"bids", "asks", "sequence"}
        assert isinstance(data["sequence"], int)
        for level in (*data["bids"], *data["asks"]):
            assert isinstance(level["price"], str)
            assert isinstance(level["quantity"], str)
            Decimal(level["price"])  # I-01: parses as decimal, never float
            Decimal(level["quantity"])

        diff = ws.receive_json()
        assert diff["type"] == "diff"
        assert diff["data"]["sequence"] > data["sequence"]


def test_intent_preview_returns_unsigned_intent_no_auth_in_mock_default(
    client: TestClient,
) -> None:
    """FE wire: POST /api/v1/execution/intent-preview, no auth header (mock default).

    Proves the backend signs nothing, holds no keys, requires no auth in the
    mock-default CI config, and returns decimal-string ``amount`` (I-01).
    """
    resp = client.post(
        "/api/v1/execution/intent-preview",
        json={"asset": "BTCUSDT", "actionType": "BUY", "notionalUsd": "100"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "sandbox-mock"
    assert body["tradable"] is True
    assert body["signed"] is False
    assert body["submitted"] is False
    order = body["order"]
    assert order is not None
    assert order["side"] == "buy"
    assert order["baseAsset"] == "BTC" and order["quoteAsset"] == "USDT"
    assert isinstance(order["amount"], str)
    Decimal(order["amount"])  # I-01: decimal-string survives the wire
    intent = body["intent"]
    assert intent is not None
    raw = intent.get("raw") or {}
    # Mock-safety: never marked submitted, even in the raw envelope.
    assert raw.get("submitted") is not True


def test_intent_preview_fail_closed_on_invalid_notional(client: TestClient) -> None:
    """FE wire: invalid input fails-closed (422), no silent fallback."""
    resp = client.post(
        "/api/v1/execution/intent-preview",
        json={"asset": "BTCUSDT", "actionType": "BUY", "notionalUsd": "0"},
    )
    assert resp.status_code == 422
