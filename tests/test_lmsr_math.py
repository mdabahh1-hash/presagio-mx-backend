"""Pure-math tests for the LMSR quote helpers (no DB)."""
import math

import pytest

from app.core import lmsr


def test_outcome_price_matches_prices_multi():
    q = {"A": 30.0, "B": -12.5, "C": 0.0}
    b = 100.0
    rounded = lmsr.prices_multi(q, b)
    for key in q:
        raw = lmsr.outcome_price(q, b, key)
        assert 0.0 < raw < 1.0
        assert round(raw * 100, 4) == rounded[key]


def test_outcome_prices_sum_to_one():
    q = {"A": 55.0, "B": 10.0, "C": -80.0, "D": 3.25}
    total = sum(lmsr.outcome_price(q, 100.0, k) for k in q)
    assert math.isclose(total, 1.0, rel_tol=1e-12)


def test_yes_price_unrounded_vs_pct():
    q_yes, q_no, b = -115.26795099383855, 0.0, 100.0
    raw = lmsr.yes_price(q_yes, q_no, b)
    assert round(raw * 100, 2) == lmsr.yes_price_pct(q_yes, q_no, b)


def test_shares_for_cost_round_trip():
    """trade_cost(shares_for_cost(x)) ≈ x — the two functions are inverses."""
    q_yes, q_no, b = 20.0, -5.0, 100.0
    for points in (1.0, 10.0, 100.0, 5000.0):
        shares = lmsr.shares_for_cost(q_yes, q_no, b, points, buy_yes=True)
        cost = lmsr.trade_cost(q_yes, q_no, b, shares, 0.0)
        assert math.isclose(cost, points, rel_tol=1e-6)


def test_avg_fill_worse_than_spot():
    """Buying always pays an average price above spot (the curve moves against you)."""
    q_yes, q_no, b = 0.0, 0.0, 100.0
    spot = lmsr.yes_price(q_yes, q_no, b)
    for points in (10.0, 100.0, 1000.0):
        shares = lmsr.shares_for_cost(q_yes, q_no, b, points, buy_yes=True)
        avg_fill = lmsr.trade_cost(q_yes, q_no, b, shares, 0.0) / shares
        assert avg_fill > spot


def test_slippage_vanishes_with_liquidity():
    """As b grows the avg fill converges to spot (deep book ⇒ no slippage).

    Around 50%, slippage ≈ shares/(8b) with shares ≈ points/0.5, so for
    100 PT: b=20 → ~125%, b=100 → ~25%, b=10k → ~0.25%, b=1M → ~0.0025%.
    """
    points = 100.0
    slippages = []
    for b in (20.0, 100.0, 10_000.0, 1_000_000.0):
        shares = lmsr.shares_for_cost(0.0, 0.0, b, points, buy_yes=True)
        avg_fill = lmsr.trade_cost(0.0, 0.0, b, shares, 0.0) / shares
        spot = 0.5
        slippages.append((avg_fill - spot) / spot)
    assert slippages[0] > slippages[1] > slippages[2] > slippages[3]
    assert slippages[2] < 0.01      # deep book: under 1%
    assert slippages[3] < 0.0001    # near-infinite book: negligible
