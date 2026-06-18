"""M1.24 — advisory-surface manifest (static config-as-data inventory, read-only, mock-safe).

characterization: manifest lists the expected advisory families; total_families == len(families);
total_endpoints == sum(endpoint_count); version == __version__; deterministic order + endpoint 200.
contract: catalogue_meta + frozen DTOs + existing endpoints unchanged.
negative-fence: NO infra/live/regulated family or path (/internal, /healthz, orders, execution,
fees, quant, market_making, marketplace, sandbox, baas) in the manifest or its config.
fail-closed: counts > 0, no fabricated family.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend import __version__
from banxe_trading_backend.app import create_app
from banxe_trading_backend.meta.catalogue import CatalogueMeta
from banxe_trading_backend.meta.manifest import (
    _ADVISORY_FAMILIES,
    AdvisorySurfaceFamily,
    AdvisorySurfaceManifest,
    advisory_surface_manifest,
)

_FORBIDDEN = (
    "/internal", "/healthz", "/metrics", "orders", "execution", "fees", "quant",
    "market_making", "market-making", "marketplace", "sandbox", "baas",
)


def test_lists_expected_advisory_families() -> None:
    m = advisory_surface_manifest()
    assert isinstance(m, AdvisorySurfaceManifest)
    fams = {e.family for e in m.families}
    assert fams == {"earn", "accounts", "assets", "symbols", "catalogue"}
    assert all(isinstance(e, AdvisorySurfaceFamily) for e in m.families)


def test_totals_and_version() -> None:
    m = advisory_surface_manifest()
    assert m.total_families == len(m.families)
    assert m.total_endpoints == sum(e.endpoint_count for e in m.families)
    assert m.total_endpoints == sum(len(v) for v in _ADVISORY_FAMILIES.values())
    assert m.version == __version__  # reused; not a second version source
    assert m.source == "sandbox-mock"
    assert all(e.endpoint_count > 0 for e in m.families)


def test_deterministic_sorted_order() -> None:
    m = advisory_surface_manifest()
    fams = [e.family for e in m.families]
    assert fams == sorted(fams)
    assert m == advisory_surface_manifest()


def test_negative_fence_no_infra_or_live_surface() -> None:
    # config-as-data must NOT contain any infra/live/regulated/sandbox family or path
    for fam, paths in _ADVISORY_FAMILIES.items():
        for bad in _FORBIDDEN:
            assert bad not in fam
            assert all(bad not in p for p in paths)
    # and the served response must not leak any forbidden token
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/advisory-surface")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"families", "totalFamilies", "totalEndpoints", "version", "source"}
    assert body["version"] == __version__
    # forbidden tokens must not appear in any served family name (source=sandbox-mock is allowed)
    served_families = {f["family"].lower() for f in body["families"]}
    for bad in _FORBIDDEN:
        assert all(bad.lower() not in fam for fam in served_families)
    txt = r.text.lower()
    assert "balance" not in txt and "uptime" not in txt and "latency" not in txt


def test_catalogue_meta_and_existing_endpoints_unchanged() -> None:
    assert set(CatalogueMeta.model_fields.keys()) == {
        "symbols_count", "instruments_count", "markets_count", "assets_count", "source", "version",
    }
    client = TestClient(create_app())
    for p in (
        "/api/v1/catalogue/meta", "/api/v1/catalogue/breakdown",
        "/api/v1/catalogue/network-breakdown", "/api/v1/catalogue/capability-breakdown",
        "/api/v1/catalogue/supported-asset-breakdown",
    ):
        assert client.get(p).status_code == 200
