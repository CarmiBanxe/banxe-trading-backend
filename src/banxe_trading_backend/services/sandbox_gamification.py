"""Educational gamification — sandbox/demo only (SBOX-5) — mock-safe.

A purely educational gamification layer over the sandbox demo flows (SBOX-2 scenarios
and SBOX-3 sessions): badges, a learning streak, scenario completions, and a
session-replay achievement. It is **demo-only**:

  * NO real money or quasi-real-money rewards; NO tokens / NFTs / anything on-chain;
  * NO variable-ratio reward schedules and NO near-miss mechanics (no gamblification);
  * NO link to real balances, volumes, or PnL — it reads only sandbox scenario /
    session / partner identifiers, all mock.

Real (G4) gamification stays operator-gated (ADR-095 cell) and is intentionally
absent. This layer activates nothing and changes no `/v1` contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

from banxe_trading_backend.models import CamelModel
from banxe_trading_backend.services.sandbox_scenarios import list_scenarios

GamificationEventType = Literal["SCENARIO_COMPLETED", "SESSION_REPLAY_VIEWED"]

_DEFAULT_PROFILE = "demo"


@dataclass(frozen=True)
class SandboxBadge:
    id: str
    title: str
    description: str


@dataclass
class SandboxStreak:
    current: int = 0
    best: int = 0


@dataclass
class SandboxGamificationState:
    profile_id: str | None
    completed_scenarios: list[str] = field(default_factory=list)
    completed_sessions: int = 0
    badges: list[SandboxBadge] = field(default_factory=list)
    streak: SandboxStreak = field(default_factory=SandboxStreak)


# ----------------------------- canonical badges ----------------------------- #

_BADGE_FIRST = SandboxBadge(
    "first-scenario", "First Steps", "Completed your first sandbox demo scenario."
)
_BADGE_ALL = SandboxBadge(
    "all-scenarios", "Full Tour", "Completed every sandbox demo scenario (SBOX-2)."
)
_BADGE_REPLAY = SandboxBadge(
    "session-replay", "Replay Watcher", "Viewed a sandbox session replay (SBOX-3)."
)


def _known_scenario_ids() -> set[str]:
    return {s.id for s in list_scenarios()}


# ----------------------------- wire (CamelModel) ---------------------------- #


class BadgeModel(CamelModel):
    id: str
    title: str
    description: str


class StreakModel(CamelModel):
    current: int
    best: int


class GamificationStateModel(CamelModel):
    profile_id: str | None
    completed_scenarios: list[str]
    completed_sessions: int
    badges: list[BadgeModel]
    streak: StreakModel


class GamificationEventRequest(CamelModel):
    profile_id: str | None = None
    event_type: GamificationEventType
    scenario_id: str | None = None
    session_id: str | None = None


# --------------------------------- store ------------------------------------ #


class SandboxGamificationStore:
    """In-memory, thread-safe educational gamification state (mock-safe; demo-only)."""

    def __init__(self) -> None:
        self._states: dict[str, SandboxGamificationState] = {}
        self._viewed_sessions: dict[str, set[str]] = {}
        self._lock = Lock()

    def _state(self, profile_id: str) -> SandboxGamificationState:
        state = self._states.get(profile_id)
        if state is None:
            state = SandboxGamificationState(profile_id=profile_id)
            self._states[profile_id] = state
            self._viewed_sessions[profile_id] = set()
        return state

    def get_state(self, profile_id: str | None) -> SandboxGamificationState:
        with self._lock:
            return self._state(profile_id or _DEFAULT_PROFILE)

    def apply_event(
        self,
        *,
        profile_id: str | None,
        event_type: GamificationEventType,
        scenario_id: str | None = None,
        session_id: str | None = None,
    ) -> SandboxGamificationState:
        with self._lock:
            state = self._state(profile_id or _DEFAULT_PROFILE)
            if event_type == "SCENARIO_COMPLETED":
                self._on_scenario(state, scenario_id)
            elif event_type == "SESSION_REPLAY_VIEWED":
                self._on_replay(state, session_id)
            return state

    def _on_scenario(self, state: SandboxGamificationState, scenario_id: str | None) -> None:
        if not scenario_id or scenario_id in state.completed_scenarios:
            return  # idempotent: no duplicate scenario, badge, or streak bump
        state.completed_scenarios.append(scenario_id)
        _bump_streak(state.streak)
        _award(state, _BADGE_FIRST)
        if _known_scenario_ids() <= set(state.completed_scenarios):
            _award(state, _BADGE_ALL)

    def _on_replay(self, state: SandboxGamificationState, session_id: str | None) -> None:
        seen = self._viewed_sessions[state.profile_id or _DEFAULT_PROFILE]
        key = session_id or "anon"
        if key in seen:
            return  # idempotent on a repeated view of the same session
        seen.add(key)
        state.completed_sessions += 1
        _bump_streak(state.streak)
        _award(state, _BADGE_REPLAY)


def _bump_streak(streak: SandboxStreak) -> None:
    streak.current += 1
    streak.best = max(streak.best, streak.current)


def _award(state: SandboxGamificationState, badge: SandboxBadge) -> None:
    if all(b.id != badge.id for b in state.badges):
        state.badges.append(badge)


# ----------------------------- model mapping -------------------------------- #


def state_model(state: SandboxGamificationState) -> GamificationStateModel:
    return GamificationStateModel(
        profile_id=state.profile_id,
        completed_scenarios=list(state.completed_scenarios),
        completed_sessions=state.completed_sessions,
        badges=[
            BadgeModel(id=b.id, title=b.title, description=b.description) for b in state.badges
        ],
        streak=StreakModel(current=state.streak.current, best=state.streak.best),
    )
