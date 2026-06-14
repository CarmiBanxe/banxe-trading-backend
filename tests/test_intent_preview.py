"""DSE → unsigned execution-intent bridge (T9.1) — internal, mock/sandbox-only.

No network, no keys, no signing/submission. Covers the advisory-action → order
mapping, notional sizing, the non-tradable path, the unsigned/not-submitted
guarantees, determinism, validation, and that nothing is exposed on the external
BaaS facade.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app
from banxe_trading_backend.config import Settings
from banxe_trading_backend.ports import InMemoryMockExchange
from banxe_trading_backend.services.intent_preview import (
    IntentPreviewRequest,
    IntentPreviewService,
)

_URL = "/api/v1/execution/intent-preview"


def _client() -> TestClient:
    return TestClient(create_app())


def _svc() -> IntentPreviewService:
    return IntentPreviewService(InMemoryMockExchange())


def _preview(**kw: object) -> dict:
    return _client().post(_URL, json=kw).json()


# --------------------------- tradable mapping ------------------------------- #


def test_open_long_maps_to_unsigned_buy_intent() -> None:
    body = _preview(asset="BTCUSDT", actionType="OPEN_LONG", notionalUsd="10000")
    assert body["tradable"] is True
    assert body["mode"] == "sandbox-mock"
    assert body["signed"] is False and body["submitted"] is False
    assert body["order"]["side"] == "buy"
    assert body["order"]["baseAsset"] == "BTC" and body["order"]["quoteAsset"] == "USDT"
    assert body["intent"] is not None
    assert body["disclaimer"]


def test_action_side_mapping() -> None:
    def side(action: str) -> str:
        return _preview(asset="BTCUSDT", actionType=action, notionalUsd="100")["order"]["side"]

    assert side("BUY") == "buy"
    assert side("SELL") == "sell"
    short = _preview(asset="ETHUSDT", actionType="OPEN_SHORT", notionalUsd="100")
    assert short["order"]["side"] == "sell"
    close = _preview(asset="ETHUSDT", actionType="CLOSE", notionalUsd="100")
    assert close["order"]["side"] == "sell" and close["order"]["reduceOnly"] is True


def test_side_override_is_respected() -> None:
    body = _preview(asset="ETHUSDT", actionType="CLOSE", notionalUsd="100", side="buy")
    assert body["order"]["side"] == "buy"  # close a short


def test_notional_is_sized_via_mock_rate() -> None:
    # mock ask = 67251.00 → amount = 10000 / 67251 (deterministic).
    body = _preview(asset="BTCUSDT", actionType="BUY", notionalUsd="10000")
    from decimal import Decimal
    assert Decimal(body["order"]["amount"]) == (Decimal("10000") / Decimal("67251.00")).quantize(
        Decimal("0.00000001")
    )


# --------------------------- non-tradable path ------------------------------ #


def test_advisory_only_actions_return_no_intent() -> None:
    for action in ("STAKE", "HEDGE", "HOLD", "WAIT", "REBALANCE", "ADJUST_SL", "SWAP"):
        body = _preview(asset="BTCUSDT", actionType=action, notionalUsd="1000")
        assert body["tradable"] is False
        assert body["order"] is None and body["intent"] is None
        assert "advisory-only" in body["reason"]


# --------------------------- safety / validation ---------------------------- #


def test_nothing_is_signed_or_submitted() -> None:
    resp = _svc()
    out = asyncio.run(resp.preview(
        IntentPreviewRequest.model_validate(
            {"asset": "BTCUSDT", "actionType": "OPEN_LONG", "notionalUsd": "5000"}
        )
    ))
    assert out.signed is False and out.submitted is False
    # The mock intent raw carries no submission.
    assert out.intent is not None
    assert (out.intent.raw or {}).get("submitted") is not True


def test_non_positive_notional_is_422() -> None:
    assert _client().post(
        _URL, json={"asset": "BTCUSDT", "actionType": "BUY", "notionalUsd": "0"}
    ).status_code == 422


def test_unsplittable_asset_is_422() -> None:
    assert _client().post(
        _URL, json={"asset": "BTC", "actionType": "BUY", "notionalUsd": "100"}
    ).status_code == 422


def test_intent_id_is_deterministic() -> None:
    a = _preview(asset="BTCUSDT", actionType="BUY", notionalUsd="100")
    b = _preview(asset="BTCUSDT", actionType="BUY", notionalUsd="100")
    assert a["intent"]["raw"] == b["intent"]["raw"]  # same clientOrderId


# ----------------------- not on the external BaaS surface ------------------- #


def test_intent_preview_not_on_external_baas_facade() -> None:
    # The /v1/... external facade must NOT expose execution intent (sandbox on).
    client = TestClient(create_app(Settings(dse_baas_sandbox_enabled=True)))
    assert client.post(
        "/v1/execution/intent-preview",
        json={"asset": "BTCUSDT", "actionType": "BUY", "notionalUsd": "100"},
    ).status_code == 404
    # Internal terminal endpoint still works.
    assert client.post(
        _URL, json={"asset": "BTCUSDT", "actionType": "BUY", "notionalUsd": "100"}
    ).status_code == 200
