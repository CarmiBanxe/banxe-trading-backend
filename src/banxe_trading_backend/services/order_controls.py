"""RED-zone order-placement controls — Ruflo + HITL gates (S6.4-EN Phase-2a).

The order-placement surface (POST/DELETE/GET /orders) sits behind two MANDATORY
controls called out by the authorising spec (BUG-005, BUG-007):

* **Ruflo (regulatory)** — every order routes through the regulatory check.
  Default sandbox-live posture is a deterministic mock allow; a live Ruflo
  provider is OPERATOR-GATED and is NOT wired this sprint. The hook is PRESENT
  on the order surface so the routing through the regulatory check is asserted
  regardless of the exchange route (mock vs dydx).

* **HITL (human-in-the-loop)** — when the exchange route resolves to the live
  ``dydx`` adapter (the FULL S6.4-EN combo, see ``resolve_exchange_route``), an
  order placement MUST carry an explicit operator confirmation header. Absent
  the confirmation the surface fail-closes with HTTP 428 — no live order is
  accepted, no submission attempted.

The surface stays **self-custodial** (ADR-083): the backend constructs an
UNSIGNED order intent. It never signs and holds NO keys; the client wallet
signs client-side. These controls are wiring + assertions, NOT a live
submission transport (Phase-2b, separate operator GO + Ruflo sign-off).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

#: Header carrying the operator HITL confirmation for a live order placement.
HITL_HEADER = "x-banxe-hitl-confirm"

#: Canonical truthy values for the HITL confirmation header.
_HITL_TRUTHY = frozenset({"1", "true", "yes", "confirmed"})


@dataclass(frozen=True)
class RufloDecision:
    """Outcome of the Ruflo regulatory check (deterministic mock allow this sprint)."""

    allowed: bool
    provider: str
    reason: str


def ruflo_check(*, client_order_id: str, owner_address: str | None) -> RufloDecision:
    """Run the regulatory Ruflo check on the order surface.

    Default sandbox-live posture: deterministic mock allow. A live Ruflo provider
    is OPERATOR-GATED and is NOT wired this sprint; this hook is PRESENT so the
    surface routes through the regulatory check regardless of the exchange route.
    Carries no secrets — only an explanatory provider/reason for observability.
    """
    return RufloDecision(allowed=True, provider="mock-ruflo", reason="sandbox-mock-allow")


def assert_ruflo_allowed(*, client_order_id: str, owner_address: str | None) -> RufloDecision:
    """Apply the Ruflo control on the order surface; fail-closed on block.

    Block maps to HTTP 451 (Unavailable For Legal Reasons), mirroring the
    ExchangePort §D3 ``ComplianceBlock`` HTTP status.
    """
    decision = ruflo_check(client_order_id=client_order_id, owner_address=owner_address)
    if not decision.allowed:
        raise HTTPException(
            status_code=451,
            detail=f"order blocked by Ruflo regulatory check: {decision.reason}",
        )
    return decision


def assert_hitl_confirmed(*, header_value: str | None) -> None:
    """Apply the HITL gate on a live-route order placement; fail-closed without confirm.

    Returns silently when the header carries a canonical truthy value (operator
    confirmation present). Otherwise raises HTTP 428 (Precondition Required) —
    no live order placement is accepted without explicit human-in-the-loop
    confirmation (BUG-007). Mock-route placements bypass this gate (caller-side).
    """
    if header_value is None or header_value.strip().lower() not in _HITL_TRUTHY:
        raise HTTPException(
            status_code=428,
            detail=(
                "HITL confirmation required for live order placement (BUG-007); "
                f"supply the {HITL_HEADER} header with a truthy value"
            ),
        )
