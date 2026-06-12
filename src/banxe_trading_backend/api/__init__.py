"""REST API layer (ADR-021 §D3) — stub routers over the mock ports."""

from .deps import get_exchange, get_market_data
from .orders import router as orders_router
from .rate import router as rate_router
from .symbols import router as symbols_router

__all__ = [
    "get_exchange",
    "get_market_data",
    "orders_router",
    "rate_router",
    "symbols_router",
]
