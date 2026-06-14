"""REST API layer — routers over the ports (ADR-021 §D3, ADR-083, ADR-084)."""

from .auth import router as auth_router
from .baas_dss import router as baas_dss_router
from .deps import get_exchange, get_market_data, get_quote_provider, get_wallet_auth
from .dss import get_dse_engine
from .dss import router as dss_router
from .earn import router as earn_router
from .execution import router as execution_router
from .internal import router as internal_router
from .orders import router as orders_router
from .quotes import router as quotes_router
from .rate import router as rate_router
from .risk import router as risk_router
from .symbols import router as symbols_router

__all__ = [
    "get_exchange",
    "get_market_data",
    "get_quote_provider",
    "get_wallet_auth",
    "get_dse_engine",
    "auth_router",
    "orders_router",
    "quotes_router",
    "rate_router",
    "symbols_router",
    "dss_router",
    "risk_router",
    "earn_router",
    "baas_dss_router",
    "internal_router",
    "execution_router",
]
