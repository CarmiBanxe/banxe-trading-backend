"""Educational gamification (SBOX-5) — internal, sandbox/demo-only, mock-safe.

No network. Covers: initial state, SCENARIO_COMPLETED (adds scenario + badge +
streak), SESSION_REPLAY_VIEWED (replay badge), idempotency (no duplicate badges),
the all-scenarios badge, not-on-/v1, and a structural assert that NO money / PnL /
volume / token field exists.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from banxe_trading_backend.app import create_app

_STATE = "/api/v1/sandbox/gamification/state"
_EVENT = "/api/v1/sandbox/gamification/event"


def _client() -> TestClient:
    return TestClient(create_app())


def _badge_ids(state: dict) -> set[str]:
    return {b["id"] for b in state["badges"]}


def test_initial_state() -> None:
    body = _client().get(_STATE).json()
    assert body["completedScenarios"] == []
    assert body["completedSessions"] == 0
    assert body["badges"] == []
    assert body["streak"] == {"current": 0, "best": 0}


def test_scenario_completed_adds_scenario_badge_and_streak() -> None:
    client = _client()
    body = client.post(
        _EVENT,
        json={"profileId": "foobank-neo", "eventType": "SCENARIO_COMPLETED",
              "scenarioId": "spot-swap-demo"},
    ).json()
    assert body["completedScenarios"] == ["spot-swap-demo"]
    assert "first-scenario" in _badge_ids(body)
    assert body["streak"]["current"] == 1 and body["streak"]["best"] == 1


def test_session_replay_viewed_awards_badge() -> None:
    client = _client()
    body = client.post(
        _EVENT,
        json={"eventType": "SESSION_REPLAY_VIEWED", "sessionId": "sess-1"},
    ).json()
    assert body["completedSessions"] == 1
    assert "session-replay" in _badge_ids(body)


def test_repeated_events_do_not_duplicate_badges() -> None:
    client = _client()
    payload = {"profileId": "p", "eventType": "SCENARIO_COMPLETED", "scenarioId": "spot-swap-demo"}
    client.post(_EVENT, json=payload)
    body = client.post(_EVENT, json=payload).json()  # same scenario again
    assert body["completedScenarios"] == ["spot-swap-demo"]  # no duplicate
    assert sorted(_badge_ids(body)) == ["first-scenario"]  # exactly one
    assert body["streak"]["current"] == 1  # idempotent: no second bump


def test_all_scenarios_badge_after_full_walkthrough() -> None:
    client = _client()
    for sid in ("spot-swap-demo", "perp-hedge-demo", "yield-rebalance-demo"):
        body = client.post(
            _EVENT, json={"profileId": "tour", "eventType": "SCENARIO_COMPLETED",
                          "scenarioId": sid},
        ).json()
    assert {"first-scenario", "all-scenarios"} <= _badge_ids(body)


def test_no_money_or_token_fields_anywhere() -> None:
    client = _client()
    client.post(_EVENT, json={"eventType": "SCENARIO_COMPLETED", "scenarioId": "spot-swap-demo"})
    state = client.get(_STATE).json()
    # Structural: exactly these descriptive keys — no balance/pnl/volume/token/reward.
    assert set(state) == {
        "profileId", "completedScenarios", "completedSessions", "badges", "streak",
    }
    blob = str(state).lower()
    for tok in ("balance", "pnl", "real", "token", "nft", "payout", "reward", "money", "volume"):
        assert tok not in blob


def test_not_on_external_v1_facade() -> None:
    client = _client()
    assert client.get("/v1/sandbox/gamification/state").status_code == 404
    assert client.get(_STATE).status_code == 200
