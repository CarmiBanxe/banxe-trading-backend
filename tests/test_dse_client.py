"""T7.4 — partner Python SDK skeleton + sandbox-collection conformance.

No network: the DSE client is exercised with a fake HTTP client, and the Postman
collection / example payloads are validated against the local OpenAPI spec.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_SPECS = _ROOT / "docs" / "specs"
sys.path.insert(0, str(_ROOT / "clients" / "python"))

import dse_client  # noqa: E402  (path injected above)


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeHttp:
    """Records the last call; returns a canned response. No network."""

    def __init__(self, status_code: int = 200, payload: Any | None = None) -> None:
        self._status = status_code
        self._payload = payload if payload is not None else {"recommendations": []}
        self.calls: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> _FakeResponse:
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        return _FakeResponse(self._status, self._payload)


def test_builds_recommend_url_from_base() -> None:
    http = _FakeHttp()
    client = dse_client.DseClient("https://sandbox.api.banxe.example/", http=http)
    client.recommend({"asset": "BTCUSDT"})
    assert http.calls[0]["url"] == "https://sandbox.api.banxe.example/v1/dss/recommend"


def test_bearer_header_present_only_with_api_key() -> None:
    http = _FakeHttp()
    dse_client.DseClient(
        "https://sandbox.api.banxe.example", api_key="abc123", http=http
    ).recommend({"asset": "BTCUSDT"})
    assert http.calls[0]["headers"]["authorization"] == "Bearer abc123"

    http2 = _FakeHttp()
    dse_client.DseClient("https://sandbox.api.banxe.example", http=http2).recommend(
        {"asset": "BTCUSDT"}
    )
    assert "authorization" not in http2.calls[0]["headers"]


def test_passes_timeout_and_returns_json_on_2xx() -> None:
    payload = {"recommendations": [{"rank": 1}]}
    http = _FakeHttp(200, payload)
    client = dse_client.DseClient(
        "https://sandbox.api.banxe.example", timeout=3.5, http=http
    )
    assert client.recommend({"asset": "BTCUSDT"}) == payload
    assert http.calls[0]["timeout"] == 3.5


def test_4xx_raises_client_error() -> None:
    http = _FakeHttp(422, {"detail": "bad"})
    client = dse_client.DseClient("https://sandbox.api.banxe.example", http=http)
    with pytest.raises(dse_client.DseClientError, match="rejected: 422"):
        client.recommend({"asset": "BTCUSDT"})


def test_5xx_raises_client_error() -> None:
    http = _FakeHttp(503, {})
    client = dse_client.DseClient("https://sandbox.api.banxe.example", http=http)
    with pytest.raises(dse_client.DseClientError, match="server error: 503"):
        client.recommend({"asset": "BTCUSDT"})


# --- sandbox collection + example-payload conformance (no network) -------------

_COLLECTION = _SPECS / "dse-baas-sandbox.postman_collection.json"
_API_SPEC = _SPECS / "dse-baas-api.yaml"


def _request_schema_props() -> set[str]:
    doc = yaml.safe_load(_API_SPEC.read_text())
    return set(doc["components"]["schemas"]["RecommendRequest"]["properties"].keys())


def test_collection_is_valid_and_sandbox_default() -> None:
    coll = json.loads(_COLLECTION.read_text())
    assert coll["info"]["name"] == "BANXE DSE Sandbox"
    variables = {v["key"]: v["value"] for v in coll["variable"]}
    # Sandbox base + placeholder key only — no real endpoint/secret.
    assert variables["baseUrl"].endswith(".example")
    assert variables["apiKey"] == "YOUR_KEY_HERE"
    assert len(coll["item"]) >= 3


def test_every_collection_item_posts_to_recommend() -> None:
    coll = json.loads(_COLLECTION.read_text())
    for item in coll["item"]:
        req = item["request"]
        assert req["method"] == "POST"
        assert req["url"]["path"] == ["v1", "dss", "recommend"]


def test_collection_example_payloads_match_request_schema() -> None:
    props = _request_schema_props()
    coll = json.loads(_COLLECTION.read_text())
    for item in coll["item"]:
        body = json.loads(item["request"]["body"]["raw"])
        unknown = set(body.keys()) - props
        assert not unknown, f"{item['name']}: unknown request keys {unknown}"
