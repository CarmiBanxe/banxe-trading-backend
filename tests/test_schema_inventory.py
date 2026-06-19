"""M1.25 — schema inventory (advisory DTO-family inventory, static config-as-data, read-only).

characterization: lists expected advisory DTO families; total_families == len; total_dtos == sum;
version == __version__; deterministic order + endpoint 200.
negative-fence: NO live/regulated/auth/orderbook/quote DTO family or name (PlaceOrder/Order/
OrderBook/Cancel/Nonce/Verify/Session/Quote/RateQuote) in config or response.
contract: catalogue_meta + advisory-surface manifest + frozen DTOs + existing endpoints unchanged.
fail-closed: counts > 0, no fabricated family.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend import __version__
from banxe_trading_backend.app import create_app
from banxe_trading_backend.meta.manifest import AdvisorySurfaceManifest
from banxe_trading_backend.meta.schema import (
    _SCHEMA_FAMILIES,
    SchemaFamily,
    SchemaInventory,
    schema_inventory,
)

_FORBIDDEN = (
    "placeorder", "exchangeorder", "orderresult", "cancel", "orderbook", "ws",
    "nonce", "verify", "session", "quote", "ratequote",
)


def test_lists_expected_advisory_dto_families() -> None:
    inv = schema_inventory()
    assert isinstance(inv, SchemaInventory)
    fams = {e.family for e in inv.families}
    assert fams == {
        "earn", "accounts", "assets", "instruments",
        "catalogue-meta", "breakdown", "manifest",
    }
    assert all(isinstance(e, SchemaFamily) for e in inv.families)


def test_totals_and_version() -> None:
    inv = schema_inventory()
    assert inv.total_families == len(inv.families)
    assert inv.total_dtos == sum(e.dto_count for e in inv.families)
    assert inv.total_dtos == sum(len(v) for v in _SCHEMA_FAMILIES.values())
    assert inv.version == __version__  # reused; not a second version source
    assert inv.source == "sandbox-mock"
    assert all(e.dto_count > 0 for e in inv.families)


def test_deterministic_sorted_order() -> None:
    inv = schema_inventory()
    fams = [e.family for e in inv.families]
    assert fams == sorted(fams)
    assert inv == schema_inventory()


def test_negative_fence_no_live_or_regulated_dto() -> None:
    # config-as-data must NOT contain any live/regulated/auth/orderbook/quote DTO name or family
    for fam, dtos in _SCHEMA_FAMILIES.items():
        for bad in _FORBIDDEN:
            assert bad not in fam.lower()
            assert all(bad not in d.lower() for d in dtos)
    # and the served response must not leak any forbidden token
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/schema-inventory")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"families", "totalFamilies", "totalDtos", "version", "source"}
    assert body["version"] == __version__
    txt = r.text.lower()
    for bad in _FORBIDDEN:
        assert bad not in txt
    assert "balance" not in txt and "apy" not in txt


def test_catalogue_meta_manifest_and_endpoints_unchanged() -> None:
    assert set(AdvisorySurfaceManifest.model_fields.keys()) == {
        "families", "total_families", "total_endpoints", "version", "source",
    }
    client = TestClient(create_app())
    for p in (
        "/api/v1/catalogue/meta", "/api/v1/catalogue/advisory-surface",
        "/api/v1/catalogue/network-breakdown", "/api/v1/catalogue/supported-asset-breakdown",
    ):
        assert client.get(p).status_code == 200
