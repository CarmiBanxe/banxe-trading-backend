"""Unified sandbox-mode surface (SBOX-1) — INTERNAL, mock-safe, read-only.

A single internal view over the already-delivered advisory seams (dss, mm-preview,
fees-preview, quant-preview, execution-intent-preview, marketplace) plus the G1L
decision-lineage logger. It reports WHAT the sandbox is — advisory-only, unsigned,
no live providers / billing / KYB — so a demo shell, a partner, or compliance can
confirm the safe posture from one place.

Strictly descriptive: it activates NOTHING, holds no keys, makes no network call,
adds no external `/v1` surface, and changes no existing contract. The flags are
derived from configuration (all providers default to mock; the app fails closed at
startup on any non-mock config), so this endpoint cannot report "live" in a
sandbox/CI deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from banxe_trading_backend.config import Settings
from banxe_trading_backend.models import CamelModel

# The advisory modules this sandbox composes (stable identifiers, not endpoints).
_ADVISORY_MODULES: tuple[str, ...] = (
    "dss",
    "mm-preview",
    "fees-preview",
    "quant-preview",
    "execution-intent-preview",
    "marketplace",
)

# Provider seams backing the advisory modules. "live" means any of these is set to a
# non-mock provider; in sandbox they are all "mock" (and non-mock fails closed at
# startup), so live_providers_enabled is False here.
_PROVIDER_SETTINGS: tuple[str, ...] = (
    "exchange_provider",
    "market_data_provider",
    "quote_provider",
    "dse_provider",
    "mm_provider",
    "fee_provider",
    "quant_provider",
    "execution_preview_provider",
)

_DISCLAIMER = (
    "Sandbox-only advisory environment. No live trading, billing, or partner "
    "activation. Everything is mock/advisory, unsigned, and fail-closed."
)


@dataclass(frozen=True)
class SandboxProfile:
    """Descriptive snapshot of the internal sandbox posture (no behaviour)."""

    mode: Literal["sandbox-demo"]
    advisory_modules: list[str]
    execution_mode: Literal["unsigned-preview-only"]
    live_providers_enabled: bool
    billing_enabled: bool
    kyb_enabled: bool
    lineage_enabled: bool
    disclaimer: str


class SandboxStatusResponse(CamelModel):
    """Wire model for ``GET /api/v1/sandbox/status`` (camelCase aliases)."""

    mode: Literal["sandbox-demo"]
    advisory_modules: list[str]
    execution_mode: Literal["unsigned-preview-only"]
    live_providers_enabled: bool
    billing_enabled: bool
    kyb_enabled: bool
    lineage_enabled: bool
    disclaimer: str


def build_sandbox_profile(settings: Settings) -> SandboxProfile:
    """Derive the sandbox profile from configuration (deterministic, no network)."""
    live = any(getattr(settings, name, "mock") != "mock" for name in _PROVIDER_SETTINGS)
    return SandboxProfile(
        mode="sandbox-demo",
        advisory_modules=list(_ADVISORY_MODULES),
        execution_mode="unsigned-preview-only",
        live_providers_enabled=live,
        # No billing / KYB exists in the estate — these are constants until an
        # operator-ratified, separately-built capability lands (ADR-095 cells).
        billing_enabled=False,
        kyb_enabled=False,
        lineage_enabled=bool(getattr(settings, "decision_lineage_enabled", True)),
        disclaimer=_DISCLAIMER,
    )


def sandbox_status_response(settings: Settings) -> SandboxStatusResponse:
    """Build the wire response from the derived profile."""
    profile = build_sandbox_profile(settings)
    return SandboxStatusResponse(
        mode=profile.mode,
        advisory_modules=profile.advisory_modules,
        execution_mode=profile.execution_mode,
        live_providers_enabled=profile.live_providers_enabled,
        billing_enabled=profile.billing_enabled,
        kyb_enabled=profile.kyb_enabled,
        lineage_enabled=profile.lineage_enabled,
        disclaimer=profile.disclaimer,
    )
