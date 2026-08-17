"""Tests for GET /markets/{id}/quote — the single source of truth for pricing."""
from decimal import Decimal

import pytest


async def _get_quote(client, market_id, **params):
    resp = await client.get(f"/api/markets/{market_id}/quote", params=params)
    return resp


async def test_deep_book_no_slippage(client, make_binary_market):
    """Deep book (huge b): avg fill ≈ spot, no warning."""
    m = await make_binary_market("deep", b=10_000.0)
    resp = await _get_quote(client, m.id, side="YES", amount=100)
    assert resp.status_code == 200
    q = resp.json()
    assert q["liquidity_warning"] is False
    assert q["slippage_pct"] < 1.0
    assert abs(q["avg_fill_price"] - q["mid_price"]) < 0.5
    assert q["spread_pct"] == 0.0


async def test_thin_book_high_slippage(client, make_binary_market):
    """Thin book (b=20): visible slippage + warning; the order moves the price."""
    m = await make_binary_market("thin", b=20.0)
    resp = await _get_quote(client, m.id, side="YES", amount=500)
    assert resp.status_code == 200
    q = resp.json()
    assert q["liquidity_warning"] is True
    assert q["slippage_pct"] > 2.0
    assert q["avg_fill_price"] > q["mid_price"]
    assert q["price_after"] > q["mid_price"]
    assert q["slippage_cost"] > 0


async def test_huge_order_fills_fully_with_warning(client, make_binary_market):
    """'Insufficient book' cannot happen in LMSR: unbounded liquidity means a
    huge order still fills completely — it just pays heavy slippage. This test
    documents that partial fills are impossible by design."""
    m = await make_binary_market("huge", b=20.0)
    resp = await _get_quote(client, m.id, side="YES", amount=100_000)
    assert resp.status_code == 200
    q = resp.json()
    assert q["shares"] > 0
    assert q["liquidity_warning"] is True
    assert q["max_loss"] == pytest.approx(100_000, rel=1e-6)


async def test_decimal_invariant_gain_equals_payout_minus_loss(client, make_binary_market):
    """potential_gain == potential_payout − max_loss EXACTLY under Decimal."""
    m = await make_binary_market("decimal-inv", b=100.0, initial_yes=0.24)
    for side in ("YES", "NO"):
        for amount in (10, 137.5, 1000):
            q = (await _get_quote(client, m.id, side=side, amount=amount)).json()
            assert Decimal(str(q["potential_gain"])) == (
                Decimal(str(q["potential_payout"])) - Decimal(str(q["max_loss"]))
            )


async def test_yes_no_mid_prices_sum_exactly_100(client, make_binary_market):
    """The informational pair must sum to exactly 100 (Decimal), even at x.5 prices."""
    # 0.235 spot → the classic 24% + 77% = 101% rounding trap
    m = await make_binary_market("sum100", b=100.0, initial_yes=0.235)
    for side in ("YES", "NO"):
        q = (await _get_quote(client, m.id, side=side, amount=50)).json()
        assert Decimal(str(q["mid_yes_price"])) + Decimal(str(q["mid_no_price"])) == Decimal("100")


async def test_no_side_uses_complement_spot(client, make_binary_market):
    """Quoting NO must price against (1 − yes_spot), not the YES price."""
    m = await make_binary_market("no-side", b=100.0, initial_yes=0.24)
    q = (await _get_quote(client, m.id, side="NO", amount=10)).json()
    assert q["mid_price"] == pytest.approx(76.0, abs=0.1)
    assert q["avg_fill_price"] >= q["mid_price"]
    # buying NO pushes the YES price down → NO spot (our side) up
    assert q["price_after"] > q["mid_price"]


async def test_multi_quote_and_sum(client, make_multi_market):
    m = await make_multi_market("multi-q", outcome_keys=("A", "B", "C"), b=100.0)
    mids = []
    for key in ("A", "B", "C"):
        resp = await _get_quote(client, m.id, outcome_key=key, amount=100)
        assert resp.status_code == 200
        q = resp.json()
        assert q["market_type"] == "multi"
        assert q["outcome_key"] == key
        assert q["avg_fill_price"] > q["mid_price"]
        mids.append(q["mid_price"])
    assert sum(mids) == pytest.approx(100.0, abs=0.02)  # 3 × 33.33


async def test_quote_validation_errors(client, make_binary_market, make_multi_market):
    mb = await make_binary_market("val-bin", b=100.0)
    mm = await make_multi_market("val-multi")
    # missing side on binary
    assert (await _get_quote(client, mb.id, amount=100)).status_code == 400
    # missing outcome_key on multi
    assert (await _get_quote(client, mm.id, amount=100)).status_code == 400
    # unknown outcome_key
    assert (await _get_quote(client, mm.id, outcome_key="ZZZ", amount=100)).status_code == 400
    # bad amounts
    assert (await _get_quote(client, mb.id, side="YES", amount=0)).status_code == 400
    assert (await _get_quote(client, mb.id, side="YES", amount=200_000)).status_code == 400
    # unknown market
    assert (await _get_quote(client, "nope", side="YES", amount=100)).status_code == 404
    # missing amount entirely
    resp = await client.get(f"/api/markets/{mb.id}/quote", params={"side": "YES"})
    assert resp.status_code == 422


async def test_quote_has_expiry(client, make_binary_market):
    from datetime import datetime, timezone
    m = await make_binary_market("expiry", b=100.0)
    q = (await _get_quote(client, m.id, side="YES", amount=100)).json()
    expires = datetime.fromisoformat(q["quote_expires_at"].replace("Z", "+00:00"))
    delta = (expires - datetime.now(timezone.utc)).total_seconds()
    assert 0 < delta <= 11
