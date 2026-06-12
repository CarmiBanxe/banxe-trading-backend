"""WebSocket layer (ADR-021 §D2) — order-book snapshot + diff."""

from .orderbook import router as orderbook_router

__all__ = ["orderbook_router"]
