"""Partner sandbox pack (SBOX-4) — INTERNAL, mock-safe, demo-only.

Sample partner profiles and demo bundles for showing the advisory product to a
prospective partner — **without any real onboarding**. There is NO KYB, NO billing /
subscriptions, NO tier activation, NO partner fee withdrawal, and NO real API keys or
tokens here. Every partner is a hard-wired, deterministic mock profile.

Real partner onboarding is a G2, operator-gated capability (ADR-095 ratify cell) and
is intentionally absent. These entities are descriptive only and activate nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from banxe_trading_backend.models import CamelModel
from banxe_trading_backend.services.sandbox_scenarios import list_scenarios

PartnerSegment = Literal["neo-bank", "wallet", "broker", "fintech-app", "exchange"]
SampleTier = Literal["sandbox-free", "sandbox-pro"]

_DISCLAIMER = (
    "Sandbox partner profile — demonstration only. No real onboarding, KYB, billing, "
    "tier activation, or keys. Live partner onboarding is operator-gated (G2)."
)

_STATUS_URL = "/api/v1/sandbox/status"
_SESSIONS_URL = "/api/v1/sandbox/sessions"
_SESSIONS_HOWTO = (
    "Open a session via POST /api/v1/sandbox/sessions, then send "
    "X-Banxe-Sandbox-Session-Id on the advisory calls to record a replayable trace "
    "(SBOX-3). Nothing is signed, submitted, or charged."
)


@dataclass(frozen=True)
class SandboxPartnerProfile:
    """A hard-wired, deterministic sample partner (no sensitive data)."""

    id: str
    slug: str
    name: str
    segment: PartnerSegment
    region: str
    use_case: str
    enabled_modules: list[str]
    sample_rate_limit_tier: SampleTier
    disclaimer: str


# ----------------------------- wire (CamelModel) ---------------------------- #


class PartnerProfileModel(CamelModel):
    id: str
    slug: str
    name: str
    segment: PartnerSegment
    region: str
    use_case: str
    enabled_modules: list[str]
    sample_rate_limit_tier: SampleTier
    disclaimer: str


class PartnersResponse(CamelModel):
    partners: list[PartnerProfileModel]


class ScenarioRef(CamelModel):
    id: str
    name: str
    tags: list[str]


class PartnerBundle(CamelModel):
    partner: PartnerProfileModel
    recommended_scenarios: list[ScenarioRef]
    sandbox_status_url: str
    sessions_url: str
    sessions_how_to: str
    disclaimers: list[str]


# ------------------------------- registry ----------------------------------- #

_PROFILES: tuple[SandboxPartnerProfile, ...] = (
    SandboxPartnerProfile(
        id="sbox-partner-foobank-neo",
        slug="foobank-neo",
        name="FooBank (neo-bank demo)",
        segment="neo-bank",
        region="EU/EEA",
        use_case="Embedded advisory trading sandbox inside a neo-bank app.",
        enabled_modules=[
            "dss", "fees-preview", "quant-preview", "execution-preview",
            "marketplace", "sessions",
        ],
        sample_rate_limit_tier="sandbox-pro",
        disclaimer=_DISCLAIMER,
    ),
    SandboxPartnerProfile(
        id="sbox-partner-walletco-demo",
        slug="walletco-demo",
        name="WalletCo (crypto wallet demo)",
        segment="wallet",
        region="Global (sandbox)",
        use_case="Crypto wallet advisory + yield sandbox.",
        enabled_modules=[
            "dss", "fees-preview", "quant-preview", "execution-preview",
            "marketplace", "sessions",
        ],
        sample_rate_limit_tier="sandbox-free",
        disclaimer=_DISCLAIMER,
    ),
    SandboxPartnerProfile(
        id="sbox-partner-brokerx-sandbox",
        slug="brokerx-sandbox",
        name="BrokerX (broker research demo)",
        segment="broker",
        region="UK",
        use_case="Broker research / analytics sandbox.",
        enabled_modules=[
            "dss", "mm-preview", "fees-preview", "quant-preview", "marketplace", "sessions",
        ],
        sample_rate_limit_tier="sandbox-pro",
        disclaimer=_DISCLAIMER,
    ),
)


def _profile_model(profile: SandboxPartnerProfile) -> PartnerProfileModel:
    return PartnerProfileModel(
        id=profile.id,
        slug=profile.slug,
        name=profile.name,
        segment=profile.segment,
        region=profile.region,
        use_case=profile.use_case,
        enabled_modules=list(profile.enabled_modules),
        sample_rate_limit_tier=profile.sample_rate_limit_tier,
        disclaimer=profile.disclaimer,
    )


def list_partners() -> list[PartnerProfileModel]:
    """Return the deterministic sample partner profiles."""
    return [_profile_model(p) for p in _PROFILES]


def _find(partner_id: str) -> SandboxPartnerProfile | None:
    for p in _PROFILES:
        if partner_id in (p.id, p.slug):
            return p
    return None


def get_partner(partner_id: str) -> PartnerProfileModel | None:
    """Return one profile by id or slug, or None if unknown."""
    profile = _find(partner_id)
    return _profile_model(profile) if profile is not None else None


def get_partner_bundle(partner_id: str) -> PartnerBundle | None:
    """Return a demo bundle (profile + recommended scenarios + how-to), or None."""
    profile = _find(partner_id)
    if profile is None:
        return None
    scenarios = [
        ScenarioRef(id=s.id, name=s.name, tags=s.tags) for s in list_scenarios()
    ]
    return PartnerBundle(
        partner=_profile_model(profile),
        recommended_scenarios=scenarios,
        sandbox_status_url=_STATUS_URL,
        sessions_url=_SESSIONS_URL,
        sessions_how_to=_SESSIONS_HOWTO,
        disclaimers=[
            _DISCLAIMER,
            "Advisory-only, unsigned, mock — no live trading, billing, or partner "
            "activation.",
        ],
    )
