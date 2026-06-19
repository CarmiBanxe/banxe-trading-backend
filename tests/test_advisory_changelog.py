"""M1.26 — advisory-surface changelog (substep provenance, static config-as-data, read-only).

characterization: ordered entries from config; total_entries == len; version == __version__; covers
M1.x substeps incl. the meta/inventory siblings; deterministic + endpoint 200.
negative-fence: NO live/regulated/auth/error token in any entry (config or response).
contract: catalogue_meta + manifest + schema-inventory + frozen DTOs + existing endpoints unchanged.
fail-closed: total_entries > 0, no fabricated entry.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend import __version__
from banxe_trading_backend.app import create_app
from banxe_trading_backend.meta.changelog import (
    _ADVISORY_CHANGELOG,
    AdvisorySurfaceChangelog,
    ChangelogEntry,
    advisory_surface_changelog,
)
from banxe_trading_backend.meta.manifest import AdvisorySurfaceManifest
from banxe_trading_backend.meta.schema import SchemaInventory

_FORBIDDEN = (
    "order", "execution", "fee", "quant", "market_making", "marketplace",
    "sandbox", "baas", "nonce", "verify", "session", "quote", "balance",
    "error", "exception", "httpexception", "uptime", "latency",
)


def test_entries_from_config_and_order() -> None:
    cl = advisory_surface_changelog()
    assert isinstance(cl, AdvisorySurfaceChangelog)
    assert all(isinstance(e, ChangelogEntry) for e in cl.entries)
    assert [(e.substep, e.title) for e in cl.entries] == list(_ADVISORY_CHANGELOG)


def test_totals_and_version() -> None:
    cl = advisory_surface_changelog()
    assert cl.total_entries == len(cl.entries)
    assert cl.total_entries == len(_ADVISORY_CHANGELOG)
    assert cl.total_entries > 0
    assert cl.version == __version__  # reused; not a second version source
    assert cl.source == "sandbox-mock"
    # covers the meta/inventory siblings (provenance completeness)
    substeps = {e.substep for e in cl.entries}
    assert {"M1.24", "M1.25", "M1.26"} <= substeps


def test_deterministic() -> None:
    assert advisory_surface_changelog() == advisory_surface_changelog()


def test_endpoint_200_and_negative_fence() -> None:
    client = TestClient(create_app())
    r = client.get("/api/v1/catalogue/changelog")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"entries", "totalEntries", "version", "source"}
    assert body["version"] == __version__
    assert body["totalEntries"] == len(body["entries"])
    # negative-fence: no live/regulated/auth/error token in config or response (excl source token)
    cfg = str(_ADVISORY_CHANGELOG).lower()
    txt = r.text.lower().replace("sandbox-mock", "")
    for bad in _FORBIDDEN:
        assert bad not in cfg
        assert bad not in txt


def test_siblings_and_endpoints_unchanged() -> None:
    assert set(AdvisorySurfaceManifest.model_fields.keys()) == {
        "families", "total_families", "total_endpoints", "version", "source",
    }
    assert set(SchemaInventory.model_fields.keys()) == {
        "families", "total_families", "total_dtos", "version", "source",
    }
    client = TestClient(create_app())
    for p in (
        "/api/v1/catalogue/meta", "/api/v1/catalogue/advisory-surface",
        "/api/v1/catalogue/schema-inventory",
    ):
        assert client.get(p).status_code == 200
