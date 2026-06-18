"""Accounts BaaS router (M1.7) -- read-only advisory account metadata.

GET /api/v1/accounts/metadata -> descriptive account types / capabilities (advisory,
sandbox-mock, config-as-data). NO balances, postings, transfers, or live ledger operations.
The canonical account/ledger source-of-truth is the Midaz LedgerPort (ADR-013); this surface
only DESCRIBES, it never operates. Does NOT touch WalletAuthPort (auth is a separate concern).
"""

from __future__ import annotations

from fastapi import APIRouter

from banxe_trading_backend.accounts.metadata import (
    AccountMetadataResponse,
    account_metadata,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/metadata", response_model=AccountMetadataResponse)
async def get_account_metadata() -> AccountMetadataResponse:
    return account_metadata()
