"""Decision-lineage / audit logging scaffold (G1L) — INTERNAL, mock-safe, inert.

A single append-only audit trail for the advisory seams (DSE / mm / fees / quant /
execution-preview). It records WHAT was asked and WHAT was answered, for a future
MiCA / AML audit. It is **inert governance scaffolding**:

  * activates NO live provider, sends NO order, holds NO keys, makes NO network call;
  * adds NO public endpoint and changes NO request/response contract;
  * **fail-closed**: any sink error is swallowed (warn-logged) and NEVER changes the
    HTTP response or business behaviour of an endpoint;
  * captures ONLY identifiers already present on the request/response — it introduces
    no new PII, and defensively redacts a denylist of sensitive keys.

This is NOT a legally sufficient audit implementation; the final policy (store,
retention, PII scope) is an OPERATOR / MLRO decision (see arch ADR-095, PROPOSED).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel

if TYPE_CHECKING:
    from fastapi import Request

LineageLayer = Literal[
    "DSE", "MM_PREVIEW", "FEE_PREVIEW", "QUANT_PREVIEW", "EXECUTION_PREVIEW"
]

_LOG = logging.getLogger("banxe.decision_lineage")

# Mock provenance stamps — there are NO live providers; these are deterministic
# placeholders so the audit record carries a version field per layer.
_MOCK_STAMP = "mock-2026-06-15"
_DEFAULT_PROVIDER_VERSIONS: dict[LineageLayer, dict[str, str]] = {
    "DSE": {"DSE": _MOCK_STAMP},
    "MM_PREVIEW": {"MM": _MOCK_STAMP},
    "FEE_PREVIEW": {"FEE": _MOCK_STAMP},
    "QUANT_PREVIEW": {"QUANT": _MOCK_STAMP},
    "EXECUTION_PREVIEW": {"EXECUTION_PREVIEW": _MOCK_STAMP},
}

# Defensive redaction — these keys must never be persisted even if a model ever
# grows one. Self-custodial today means none of these are present, but the audit
# store must stay safe by construction.
_REDACT_KEYS = frozenset(
    {
        "owner_address",
        "owneraddress",
        "private_key",
        "privatekey",
        "signature",
        "signed_tx",
        "session",
        "session_token",
        "token",
        "api_key",
        "apikey",
        "secret",
        "password",
        "mnemonic",
        "seed",
    }
)


@dataclass(frozen=True)
class DecisionLineageEvent:
    """One immutable audit record for a single advisory request/response."""

    id: str
    timestamp: datetime
    layer: LineageLayer
    partner_id: str | None
    user_id: str | None
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    provider_versions: dict[str, str]
    correlation_id: str | None
    rationale: str | None


class LineageSink(Protocol):
    """Append-only destination for audit events (no read API by design)."""

    def write(self, event: DecisionLineageEvent) -> None: ...


class LoggingLineageSink:
    """Default sink: append-only JSON-lines onto the package logging stream.

    Uses the existing ``logging`` stack only (no external store / SIEM). One JSON
    object per line, stable key order — greppable and forwardable by deployment.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._log = logger or logging.getLogger("banxe.decision_lineage.audit")

    def write(self, event: DecisionLineageEvent) -> None:
        self._log.info(json.dumps(_event_to_json(event), separators=(",", ":"), sort_keys=True))


class DecisionLineageLogger:
    """Records :class:`DecisionLineageEvent`s to a sink, fail-closed.

    ``enabled=False`` makes every call a silent no-op. A failing sink never
    propagates — it is caught and warn-logged so the calling endpoint is unaffected.
    """

    def __init__(self, sink: LineageSink | None = None, *, enabled: bool = True) -> None:
        self._sink = sink or LoggingLineageSink()
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def log(self, event: DecisionLineageEvent) -> None:
        if not self._enabled:
            return
        try:
            self._sink.write(event)
        except Exception as exc:  # noqa: BLE001 - fail-closed: audit must never break flow
            _LOG.warning("decision-lineage write failed (%s); business flow unaffected", exc)

    def record(
        self,
        *,
        layer: LineageLayer,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        provider_versions: dict[str, str] | None = None,
        partner_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
        rationale: str | None = None,
    ) -> str:
        """Build an event (id/timestamp/correlation defaulted) and log it.

        Returns the correlation id used (generated if not supplied). When disabled,
        returns the supplied/empty correlation id without building an event.
        """
        if not self._enabled:
            return correlation_id or ""
        corr = correlation_id or str(uuid4())
        event = DecisionLineageEvent(
            id=str(uuid4()),
            timestamp=datetime.now(UTC),
            layer=layer,
            partner_id=partner_id,
            user_id=user_id,
            request_payload=request_payload,
            response_payload=response_payload,
            provider_versions=dict(provider_versions or _DEFAULT_PROVIDER_VERSIONS[layer]),
            correlation_id=corr,
            rationale=rationale,
        )
        self.log(event)
        return corr


def build_decision_lineage_logger(settings: Any) -> DecisionLineageLogger:
    """Factory used by ``create_app`` — mock-safe; honours the enable flag."""
    enabled = bool(getattr(settings, "decision_lineage_enabled", True))
    return DecisionLineageLogger(enabled=enabled)


def record_lineage(
    request: Request,
    *,
    layer: LineageLayer,
    body: Any,
    response: Any,
    provider_versions: dict[str, str] | None = None,
    rationale: str | None = None,
) -> None:
    """Endpoint-side helper: capture one audit event, defensively.

    Reads the logger from ``app.state`` (absent → no-op) and is itself wrapped so a
    capture failure can never change the endpoint's behaviour.
    """
    logger: DecisionLineageLogger | None = getattr(
        request.app.state, "decision_lineage_logger", None
    )
    if logger is None or not logger.enabled:
        return
    try:
        partner_id, user_id = _extract_principals(body)
        logger.record(
            layer=layer,
            request_payload=_to_payload(body),
            response_payload=_to_payload(response),
            provider_versions=provider_versions,
            partner_id=partner_id,
            user_id=user_id,
            correlation_id=_extract_correlation(response),
            rationale=rationale,
        )
    except Exception as exc:  # noqa: BLE001 - fail-closed: never affect the response
        _LOG.warning("decision-lineage capture failed (%s); business flow unaffected", exc)


def _extract_principals(body: Any) -> tuple[str | None, str | None]:
    """Pull partner/user identifiers that ALREADY exist on the request (else None)."""
    partner_id: str | None = None
    partner_context = getattr(body, "partner_context", None)
    if partner_context is not None:
        partner_id = getattr(partner_context, "partner_id", None)
    if partner_id is None:
        partner_id = getattr(body, "integrator_id", None)
    user_id: str | None = getattr(body, "user_id", None)
    return partner_id, user_id


def _extract_correlation(response: Any) -> str | None:
    return getattr(response, "correlation_id", None)


def _to_payload(obj: Any) -> dict[str, Any]:
    """Serialise a request/response to a redacted JSON-safe dict."""
    if obj is None:
        return {}
    data: Any
    if isinstance(obj, BaseModel):
        data = obj.model_dump(mode="json")
    elif is_dataclass(obj) and not isinstance(obj, type):
        data = asdict(obj)
    elif isinstance(obj, dict):
        data = obj
    else:
        return {"repr": str(obj)}
    redacted = _redact(data)
    return redacted if isinstance(redacted, dict) else {"value": redacted}


def _redact(value: Any) -> Any:
    """Recursively drop denylisted keys; values themselves are untouched."""
    if isinstance(value, dict):
        return {
            k: _redact(v)
            for k, v in value.items()
            if str(k).lower() not in _REDACT_KEYS
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _event_to_json(event: DecisionLineageEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "timestamp": event.timestamp.isoformat(),
        "layer": event.layer,
        "partnerId": event.partner_id,
        "userId": event.user_id,
        "correlationId": event.correlation_id,
        "providerVersions": event.provider_versions,
        "rationale": event.rationale,
        "request": event.request_payload,
        "response": event.response_payload,
    }
