from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient


def _assert_level_shape(level: dict[str, object]) -> None:
    assert isinstance(level["price"], str)
    assert isinstance(level["quantity"], str)
    Decimal(level["price"])  # decimal-string (I-01)
    Decimal(level["quantity"])


def test_ws_emits_snapshot_then_diff(client: TestClient) -> None:
    with client.websocket_connect("/ws/orderbook/BTC-EUR") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot"
        snap_data = snap["data"]
        assert {"bids", "asks", "sequence"} <= set(snap_data)
        assert snap_data["sequence"] == 1
        assert snap_data["bids"] and snap_data["asks"]
        _assert_level_shape(snap_data["bids"][0])
        _assert_level_shape(snap_data["asks"][0])

        diff = ws.receive_json()
        assert diff["type"] == "diff"
        diff_data = diff["data"]
        assert {"bids", "asks", "sequence"} <= set(diff_data)
        # strictly increasing sequence vs the snapshot
        assert diff_data["sequence"] > snap_data["sequence"]


def test_ws_diffs_have_monotonic_sequence(client: TestClient) -> None:
    with client.websocket_connect("/ws/orderbook/BTC-EUR") as ws:
        snap = ws.receive_json()
        last = snap["data"]["sequence"]
        seen_diffs = 0
        for _ in range(3):
            msg = ws.receive_json()
            assert msg["type"] == "diff"
            assert msg["data"]["sequence"] > last
            last = msg["data"]["sequence"]
            seen_diffs += 1
        assert seen_diffs == 3
