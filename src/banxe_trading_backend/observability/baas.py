"""DSE BaaS observability primitives (T8.2) — metrics, structured log, health.

INTERNAL ONLY. Advisory/mock — these are readiness signals for a future prod
rollout; they add no public contract, no execution, no secrets, no PII. Metrics
render in Prometheus text-exposition format (also trivially shippable to StatsD /
a log stream); the structured log is sanitized aggregate/anonymized summary only.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from threading import Lock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from banxe_trading_backend.dse import DseEngine

#: Structured-log channel for DSE BaaS events (JSON lines; no secrets/PII).
_LOG = logging.getLogger("banxe.dse.baas")


def _esc(value: str) -> str:
    """Escape a Prometheus label value."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class BaasMetrics:
    """In-process DSE BaaS counters/latency — exportable as Prometheus text.

    Labels are LOW-cardinality, NON-sensitive only: asset symbol, riskProfile,
    HTTP status, actionType. No user identifiers, amounts, or positions.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latency_sum_ms: dict[tuple[str, str], float] = defaultdict(float)
        self._latency_count: dict[tuple[str, str], int] = defaultdict(int)
        self._top_action: dict[str, int] = defaultdict(int)
        self._by_mode: dict[str, int] = defaultdict(int)
        self._debug_requests = 0
        self._total = 0

    def observe(
        self,
        *,
        asset: str,
        risk_profile: str,
        status: int,
        latency_ms: float,
        top_action_type: str | None = None,
        debug: bool = False,
        provider_mode: str = "mock",
    ) -> None:
        with self._lock:
            self._total += 1
            self._requests[(asset, risk_profile, status)] += 1
            self._latency_sum_ms[(asset, risk_profile)] += latency_ms
            self._latency_count[(asset, risk_profile)] += 1
            self._by_mode[provider_mode] += 1
            if top_action_type is not None:
                self._top_action[top_action_type] += 1
            if debug:
                self._debug_requests += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "totalRequests": self._total,
                "debugRequests": self._debug_requests,
                "statuses": {
                    str(status): n
                    for (_, _, status), n in sorted(self._requests.items())
                },
            }

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            lines.append("# HELP dse_baas_requests_total DSE BaaS facade requests.")
            lines.append("# TYPE dse_baas_requests_total counter")
            for (asset, profile, status), n in sorted(self._requests.items()):
                lines.append(
                    f'dse_baas_requests_total{{asset="{_esc(asset)}",'
                    f'risk_profile="{_esc(profile)}",status="{status}"}} {n}'
                )
            lines.append("# HELP dse_baas_request_latency_ms_sum Sum of facade latency (ms).")
            lines.append("# TYPE dse_baas_request_latency_ms_sum counter")
            for (asset, profile), total in sorted(self._latency_sum_ms.items()):
                lines.append(
                    f'dse_baas_request_latency_ms_sum{{asset="{_esc(asset)}",'
                    f'risk_profile="{_esc(profile)}"}} {total:.3f}'
                )
            lines.append("# HELP dse_baas_request_latency_count Facade request count (per label).")
            lines.append("# TYPE dse_baas_request_latency_count counter")
            for (asset, profile), n in sorted(self._latency_count.items()):
                lines.append(
                    f'dse_baas_request_latency_count{{asset="{_esc(asset)}",'
                    f'risk_profile="{_esc(profile)}"}} {n}'
                )
            lines.append("# HELP dse_baas_top_action_total Top-recommendation actionType counts.")
            lines.append("# TYPE dse_baas_top_action_total counter")
            for action, n in sorted(self._top_action.items()):
                lines.append(f'dse_baas_top_action_total{{action_type="{_esc(action)}"}} {n}')
            lines.append("# HELP dse_baas_debug_requests_total Requests that opted into debug.")
            lines.append("# TYPE dse_baas_debug_requests_total counter")
            lines.append(f"dse_baas_debug_requests_total {self._debug_requests}")
            lines.append(
                "# HELP dse_baas_requests_by_mode_total Requests by DSE provider mode."
            )
            lines.append("# TYPE dse_baas_requests_by_mode_total counter")
            for mode, n in sorted(self._by_mode.items()):
                lines.append(f'dse_baas_requests_by_mode_total{{provider_mode="{_esc(mode)}"}} {n}')
        return "\n".join(lines) + "\n"


def log_baas_event(event: dict[str, Any]) -> None:
    """Emit a sanitized structured DSE BaaS event (JSON line).

    The caller MUST pass only aggregate/anonymized fields — never secrets, keys,
    raw payloads, amounts, positions or any KYC/personal data.
    """
    _LOG.info(json.dumps(event, separators=(",", ":"), sort_keys=True))


async def dse_baas_health(
    *,
    sandbox_enabled: bool,
    engine: DseEngine,
    provider_mode: str = "mock",
    foundation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Internal readiness check: flag + a no-network mock dry-run of the DSE.

    Returns an aggregated status (OK | DEGRADED | ERROR) and a short summary.
    DEGRADED means the component is alive but the sandbox facade is gated off;
    ERROR means the internal engine dry-run failed.
    """
    from banxe_trading_backend.dse import RecommendRequest

    checks: dict[str, Any] = {
        "sandboxEnabled": sandbox_enabled,
        "providerMode": provider_mode,
        "foundation": foundation or {},
    }
    status = "OK" if sandbox_enabled else "DEGRADED"
    try:
        resp = await engine.recommend(
            RecommendRequest(asset="BTCUSDT", portfolio_value_usd="1000")
        )
        healthy = bool(resp.recommendations)
        checks["dryRun"] = "ok" if healthy else "empty"
        checks["recommendationCount"] = len(resp.recommendations)
        if not healthy:
            status = "ERROR"
    except Exception as exc:  # dry-run must never raise in a healthy mock engine
        checks["dryRun"] = "error"
        checks["error"] = type(exc).__name__
        status = "ERROR"
    summary = {
        "OK": "DSE sandbox enabled, mock providers healthy",
        "DEGRADED": "DSE internal engine healthy; BaaS sandbox facade disabled (flag off)",
        "ERROR": "DSE internal engine dry-run failed",
    }[status]
    return {"status": status, "summary": summary, "checks": checks}
