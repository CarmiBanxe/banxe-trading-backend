"""DSE partner/product surface (Sprint S11) — non-breaking, advisory, mock-safe.

Builds the optional, opt-in ``product`` metadata block for the recommend response:
safe provider provenance (tier class per domain), normalized model/version
exposure, the explainability model, advisory/self-custodial flags, and a
correlation id. It is populated ONLY when the request supplies ``partnerContext``.

Strictly product-safe: NO secrets, NO raw env, NO credentials, NO billing/auth.
Only "sandbox" partner mode is supported — anything else FAILS CLOSED (the caller
maps the ValueError to 422). It changes NO utility and NO ranking.
"""

from __future__ import annotations

from .models import (
    ModelVersions,
    PartnerContext,
    ProductMetadata,
    RecommendRequest,
)

_SURFACE = "dse-baas-sandbox"
_ENGINE_MODE = "sandbox-mock"
_DETERMINISM = "deterministic-mock"
_EXPLANATION_MODEL = "U_a = w1·ER − w2·σ − w3·VaR99 − w4·DD + w5·Liq"
_PRODUCT_DISCLAIMER = (
    "Advisory decision-support (sandbox / mock data). NOT an order, NOT execution, "
    "NO signing and NO custody — self-custodial. Per MiCA / MiFID II this is "
    "decision-support output, not investment advice. No SLA, billing or partner "
    "entitlement is implied."
)
_DOMAINS = ("market", "sentiment", "stress")


def _provenance_class(tier: str) -> str:
    """Map a foundation tier to a safe provenance class label."""
    return "inert-live-ready" if tier == "live-ready" else tier


def build_product_metadata(
    request: RecommendRequest,
    *,
    model_versions: ModelVersions,
    explanation_version: str,
    request_id: str,
    foundation_profile: dict[str, dict[str, str]],
) -> ProductMetadata:
    """Assemble the opt-in product block (fail-closed on non-sandbox mode)."""
    partner: PartnerContext | None = request.partner_context
    if partner is not None and partner.mode != "sandbox":
        raise ValueError(
            f"partner mode {partner.mode!r} is OPERATOR DECISION REQUIRED "
            "(sandbox-only; no production partner mode is wired)"
        )
    provenance = {
        domain: _provenance_class(foundation_profile.get(domain, {}).get("tier", "mock"))
        for domain in _DOMAINS
    }
    return ProductMetadata(
        surface=_SURFACE,
        engine_mode=_ENGINE_MODE,
        advisory=True,
        executes=False,
        self_custodial=True,
        determinism=_DETERMINISM,
        provider_provenance=provenance,
        model_versions=model_versions,
        explanation_version=explanation_version,
        explanation_model=_EXPLANATION_MODEL,
        request_id=request_id,
        partner=partner,
        disclaimer=_PRODUCT_DISCLAIMER,
    )
