"""Internal observability for the DSE BaaS sandbox (T8.2).

Pure internal readiness/observability — NO public-contract change, NO secrets,
NO PII. Metrics + structured logs + a health dry-run for future prod-rollout.
"""

from .baas import (
    BaasMetrics,
    dse_baas_health,
    log_baas_event,
)

__all__ = ["BaasMetrics", "dse_baas_health", "log_baas_event"]
