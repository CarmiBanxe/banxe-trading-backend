"""REST API layer — routers over the ports (ADR-021 §D3, ADR-083 D4)."""

from .auth import router as auth_router
from .deps import get_exchange, get_market_data, get_wallet_auth
from .orders import router as orders_router
from .rate import router as rate_router
from .symbols import router as symbols_router

__all__ = [
    "get_exchange",
    "get_market_data",
    "get_wallet_auth",
    "auth_router",
    "orders_router",
    "rate_router",
    "symbols_router",
]
