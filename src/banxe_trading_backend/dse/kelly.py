"""Kelly / Half-Kelly position sizing (T7.1) — pure Decimal (I-01, no float).

f* = (p*(b+1) - 1) / b, clamped to [0, 1], where p = win rate and b = win/loss
ratio. **Half-Kelly (f*/2) is the hard-limit default** surfaced to users.
"""

from __future__ import annotations

from decimal import Decimal

_ZERO = Decimal(0)
_ONE = Decimal(1)


def kelly_fraction(win_rate: Decimal, win_loss_ratio: Decimal) -> Decimal:
    """Full Kelly fraction, clamped to [0, 1]. Returns 0 for non-positive edge."""
    if win_loss_ratio <= _ZERO:
        return _ZERO
    f = (win_rate * (win_loss_ratio + _ONE) - _ONE) / win_loss_ratio
    if f < _ZERO:
        return _ZERO
    if f > _ONE:
        return _ONE
    return f


def half_kelly_fraction(win_rate: Decimal, win_loss_ratio: Decimal) -> Decimal:
    """Hard-limit default sizing = full Kelly / 2."""
    return kelly_fraction(win_rate, win_loss_ratio) / Decimal(2)
