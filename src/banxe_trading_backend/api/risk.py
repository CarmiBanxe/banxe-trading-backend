"""Risk BaaS router (T7.5) — read-only sandbox Risk analytics.

GET /api/v1/risk/greeks → portfolio-level Greeks (advisory, sandbox-mock). The
external BaaS path is GET /v1/risk/greeks (see docs/specs/risk-api.yaml); Kong /
partner keys / rate limits are out of scope this sprint. READ-ONLY: no execution,
no signing, no stake/unstake (self-custodial). Future Risk endpoints (var, stress,
pnl) are NOT part of T7.5.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, Query, Request

from banxe_trading_backend.risk.greeks import (
    PortfolioGreeksResponse,
    RiskGreeksProvider,
    portfolio_greeks,
)

router = APIRouter(prefix="/risk", tags=["risk"])


def _decimal(value: str, field: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail=f"invalid decimal {field!r}") from exc


@router.get("/greeks", response_model=PortfolioGreeksResponse)
async def get_greeks(
    request: Request,
    asset: str = Query(..., description="target asset, e.g. BTCUSDT"),
    portfolio_value_usd: str | None = Query(None, alias="portfolioValueUsd"),
    position_usd: str | None = Query(None, alias="positionUsd"),
    side: str = Query("long", pattern="^(long|short|spot)$"),
) -> PortfolioGreeksResponse:
    # Net notional defaults to the position, else the whole portfolio, else 0.
    notional = _decimal(position_usd or portfolio_value_usd or "0", "positionUsd")
    portfolio = _decimal(portfolio_value_usd or position_usd or "0", "portfolioValueUsd")
    provider: RiskGreeksProvider = request.app.state.risk_greeks
    return portfolio_greeks(
        provider,
        asset=asset,
        notional_usd=notional,
        side=side,
        portfolio_usd=portfolio,
        now=datetime.now(UTC).isoformat(),
    )
