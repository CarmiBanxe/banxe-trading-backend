"""Sandbox session recorder & replay (SBOX-3) — INTERNAL, mock-safe, advisory-only.

An observability layer that ties several demo-scenario steps into one sandbox
session and links each to the G1L decision-lineage events already produced per
request. It stores ONLY data already present in the advisory payloads / G1L events
(no new PII), adds no live capability, and changes no existing behaviour.

Storage is a simple in-memory store (no external service, no separate log). The
store also exposes ``attach_lineage`` so the G1L helper can append a lineage step
to an open session when a request carries the sandbox-session header — best-effort
and fail-closed (an unknown session is ignored).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Literal
from uuid import uuid4

from banxe_trading_backend.models import CamelModel

SessionLayer = Literal[
    "DSE",
    "MM_PREVIEW",
    "FEE_PREVIEW",
    "QUANT_PREVIEW",
    "EXECUTION_PREVIEW",
    "MARKETPLACE",
]

# Header a demo run may send so advisory requests attach their lineage to a session.
SANDBOX_SESSION_HEADER = "X-Banxe-Sandbox-Session-Id"

_MAX_LIMIT = 200


@dataclass(frozen=True)
class SandboxSessionStepRef:
    """A reference to one recorded step (scenario step and/or a lineage event)."""

    scenario_id: str | None
    step_id: str | None
    layer: SessionLayer
    lineage_event_id: str | None


@dataclass
class SandboxSessionSummary:
    """A sandbox session: an ordered set of step references plus metadata."""

    id: str
    started_at: datetime
    finished_at: datetime | None
    scenario_id: str | None
    title: str
    description: str
    steps: list[SandboxSessionStepRef] = field(default_factory=list)
    notes: str | None = None


# ----------------------------- wire (CamelModel) ---------------------------- #


class SessionStepRefModel(CamelModel):
    scenario_id: str | None
    step_id: str | None
    layer: SessionLayer
    lineage_event_id: str | None


class SessionSummaryModel(CamelModel):
    id: str
    started_at: datetime
    finished_at: datetime | None
    scenario_id: str | None
    title: str
    description: str
    steps: list[SessionStepRefModel]
    notes: str | None


class SessionsListResponse(CamelModel):
    sessions: list[SessionSummaryModel]


class CreateSessionRequest(CamelModel):
    scenario_id: str | None = None
    title: str
    description: str = ""


class AppendStepRequest(CamelModel):
    scenario_id: str | None = None
    step_id: str | None = None
    layer: SessionLayer
    lineage_event_id: str | None = None


class FinishSessionRequest(CamelModel):
    notes: str | None = None


# --------------------------------- store ------------------------------------ #


class SandboxSessionStore:
    """In-memory, thread-safe sandbox-session store (mock-safe; no persistence)."""

    def __init__(self) -> None:
        self._sessions: dict[str, SandboxSessionSummary] = {}
        self._order: list[str] = []
        self._lock = Lock()

    def create_session(
        self, *, scenario_id: str | None, title: str, description: str
    ) -> SandboxSessionSummary:
        with self._lock:
            session_id = str(uuid4())
            summary = SandboxSessionSummary(
                id=session_id,
                started_at=datetime.now(UTC),
                finished_at=None,
                scenario_id=scenario_id,
                title=title,
                description=description,
            )
            self._sessions[session_id] = summary
            self._order.append(session_id)
            return summary

    def append_step(
        self, session_id: str, step: SandboxSessionStepRef
    ) -> SandboxSessionSummary | None:
        with self._lock:
            summary = self._sessions.get(session_id)
            if summary is None:
                return None
            summary.steps.append(step)
            return summary

    def finish_session(
        self, session_id: str, notes: str | None = None
    ) -> SandboxSessionSummary | None:
        with self._lock:
            summary = self._sessions.get(session_id)
            if summary is None:
                return None
            summary.finished_at = datetime.now(UTC)
            if notes is not None:
                summary.notes = notes
            return summary

    def get_session(self, session_id: str) -> SandboxSessionSummary | None:
        return self._sessions.get(session_id)

    def list_sessions(self, *, limit: int, offset: int) -> list[SandboxSessionSummary]:
        bounded = max(0, min(limit, _MAX_LIMIT))
        start = max(0, offset)
        with self._lock:
            ids = self._order[start : start + bounded]
            return [self._sessions[i] for i in ids]

    def attach_lineage(self, session_id: str, layer: SessionLayer, lineage_event_id: str) -> None:
        """Best-effort: append a lineage-only step to an open session (else ignore)."""
        self.append_step(
            session_id,
            SandboxSessionStepRef(
                scenario_id=None, step_id=None, layer=layer, lineage_event_id=lineage_event_id
            ),
        )


# ----------------------------- model mapping -------------------------------- #


def _step_model(step: SandboxSessionStepRef) -> SessionStepRefModel:
    return SessionStepRefModel(
        scenario_id=step.scenario_id,
        step_id=step.step_id,
        layer=step.layer,
        lineage_event_id=step.lineage_event_id,
    )


def session_summary_model(summary: SandboxSessionSummary) -> SessionSummaryModel:
    return SessionSummaryModel(
        id=summary.id,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        scenario_id=summary.scenario_id,
        title=summary.title,
        description=summary.description,
        steps=[_step_model(s) for s in summary.steps],
        notes=summary.notes,
    )
