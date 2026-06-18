"""Earn advisory provider seam (T7.3) — yield rates, mock default.

Advisory-only (ADR-084/085): yields are estimates/simulations, NOT a promise of
return. NO execution, NO keys, NO network. Real StakeKit / Aave-style providers
are OPERATOR-GATED future sprints behind the same ``EarnRatesProvider`` Protocol.
"""

from .providers import (
    EarnRatesProvider,
    MockEarnRatesProvider,
    build_earn_provider,
)
from .rates import (
    DEFAULT_BASKET,
    EarnRatesCatalog,
    EarnRatesResponse,
    MockEarnRatesCatalog,
    RateCard,
    RiskBand,
    build_earn_rates_catalog,
    earn_rates,
)
from .statement import (
    EarnStatement,
    EarnStatementResponse,
    earn_statement,
)
from .status import (
    EarnAdvisoryStatus,
    from_legacy,
)
from .taxonomy import EarnTaxonomy, earn_taxonomy

__all__ = [
    "EarnRatesProvider",
    "MockEarnRatesProvider",
    "build_earn_provider",
    "EarnRatesCatalog",
    "MockEarnRatesCatalog",
    "EarnRatesResponse",
    "RateCard",
    "RiskBand",
    "DEFAULT_BASKET",
    "build_earn_rates_catalog",
    "earn_rates",
    "EarnAdvisoryStatus",
    "EarnTaxonomy",
    "earn_taxonomy",
    "from_legacy",
    "EarnStatement",
    "EarnStatementResponse",
    "earn_statement",
]
