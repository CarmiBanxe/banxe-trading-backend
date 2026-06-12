"""Order-book WebSocket endpoint (ADR-021 §D2).

On connect: send one ``snapshot`` envelope, then stream ``diff`` envelopes from
the MarketDataPort. Envelopes are the verbatim FE ``WsMessage`` shapes
(``{type, data:{bids, asks, sequence}}``) with decimal-string prices/quantities
(I-01). ``sequence`` is strictly increasing; on gap/reconnect a fresh snapshot
is sent (the FE store drops stale diffs). The skeleton's mock source is finite;
a real provider would stream continuously.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from banxe_trading_backend.models import WsDiffMessage, WsSnapshotMessage
from banxe_trading_backend.ports import MarketDataPort

router = APIRouter()


@router.websocket("/ws/orderbook/{symbol}")
async def orderbook_ws(websocket: WebSocket, symbol: str) -> None:
    market_data: MarketDataPort = websocket.app.state.market_data
    await websocket.accept()
    try:
        snapshot = await market_data.get_snapshot(symbol)
        await websocket.send_json(WsSnapshotMessage(data=snapshot).model_dump(by_alias=True))
        async for diff in market_data.stream_diffs(symbol):
            await websocket.send_json(WsDiffMessage(data=diff).model_dump(by_alias=True))
    except WebSocketDisconnect:
        return
