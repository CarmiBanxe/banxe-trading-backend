"""Partner sandbox-pack router (SBOX-4) — INTERNAL, mock-safe, read-only.

GET /api/v1/sandbox/partners              → sample partner profiles
GET /api/v1/sandbox/partners/{id}         → one profile (by id or slug)
GET /api/v1/sandbox/partners/{id}/bundle  → a demo bundle (profile + scenarios + how-to)

Hard-wired mock partners for demonstrations — NO real onboarding, KYB, billing, tier
activation, or keys. Internal terminal endpoints — NOT on the external `/v1` facade.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from banxe_trading_backend.services.sandbox_partner_profiles import (
    PartnerBundle,
    PartnerProfileModel,
    PartnersResponse,
    get_partner,
    get_partner_bundle,
    list_partners,
)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


@router.get("/partners", response_model=PartnersResponse)
async def partners() -> PartnersResponse:
    return PartnersResponse(partners=list_partners())


@router.get("/partners/{partner_id}", response_model=PartnerProfileModel)
async def partner_detail(partner_id: str) -> PartnerProfileModel:
    profile = get_partner(partner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"partner {partner_id!r} not found")
    return profile


@router.get("/partners/{partner_id}/bundle", response_model=PartnerBundle)
async def partner_bundle(partner_id: str) -> PartnerBundle:
    bundle = get_partner_bundle(partner_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"partner {partner_id!r} not found")
    return bundle
