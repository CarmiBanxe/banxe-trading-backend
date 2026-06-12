from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient


def _is_decimal_str(value: object) -> bool:
    if not isinstance(value, str):
        return False
    Decimal(value)  # raises if not a decimal string
    return True


def test_place_order_returns_order_result(client: TestClient) -> None:
    body = {
        "symbol": "BTC-EUR",
        "side": "buy",
        "type": "limit",
        "amount": "0.5",
        "limitPrice": "67000.00",
        "clientOrderId": "11111111-1111-4111-8111-111111111111",
        "correlationId": "corr-1",
    }
    resp = client.post("/api/v1/orders", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["orderId"].startswith("mock-")
    assert data["state"] in {"accepted", "filled", "partial", "rejected", "expired", "cancelled"}
    assert _is_decimal_str(data["filledAmount"])


def test_place_order_is_idempotent_on_client_order_id(client: TestClient) -> None:
    body = {
        "symbol": "BTC-EUR",
        "side": "buy",
        "type": "market",
        "amount": "1",
        "clientOrderId": "22222222-2222-4222-8222-222222222222",
        "correlationId": "corr-2",
    }
    first = client.post("/api/v1/orders", json=body).json()
    second = client.post("/api/v1/orders", json=body).json()
    assert first["orderId"] == second["orderId"]  # replay -> same order, no double-execute


def test_place_order_rejects_float_amount_i01(client: TestClient) -> None:
    body = {
        "symbol": "BTC-EUR",
        "side": "buy",
        "type": "market",
        "amount": 0.5,  # float money is forbidden (I-01)
        "clientOrderId": "33333333-3333-4333-8333-333333333333",
        "correlationId": "corr-3",
    }
    resp = client.post("/api/v1/orders", json=body)
    assert resp.status_code == 422


def test_cancel_order_returns_bool(client: TestClient) -> None:
    resp = client.delete("/api/v1/orders/unknown-id")
    assert resp.status_code == 200
    data = resp.json()
    assert data["orderId"] == "unknown-id"
    assert data["cancelled"] is False  # unknown -> False, no error (idempotent)


def test_order_status_returns_order_result(client: TestClient) -> None:
    resp = client.get("/api/v1/orders/mock-000001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["orderId"] == "mock-000001"
    assert "state" in data


def test_rate_returns_quote(client: TestClient) -> None:
    resp = client.get("/api/v1/rate", params={"base": "BTC", "quote": "EUR"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["baseAsset"] == "BTC"
    assert data["quoteAsset"] == "EUR"
    assert _is_decimal_str(data["bid"]) and _is_decimal_str(data["ask"])
    assert data["ttlSeconds"] > 0


def test_symbols_returns_catalogue(client: TestClient) -> None:
    resp = client.get("/api/v1/symbols")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list) and len(items) >= 1
    first = items[0]
    assert {"symbol", "baseAsset", "quoteAsset", "pricePrecision", "qtyPrecision", "status"} <= set(
        first
    )


def test_instrument_returns_descriptor(client: TestClient) -> None:
    resp = client.get("/api/v1/instruments/BTC-EUR")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTC-EUR"
    assert _is_decimal_str(data["tickSize"])
    assert _is_decimal_str(data["minQty"]) and _is_decimal_str(data["maxQty"])
