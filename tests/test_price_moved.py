"""PRICE_MOVED protection: stale quotes are rejected with 409, state untouched."""
import pytest
from sqlalchemy import select

from tests.conftest import auth_headers
from app.models.market import Market
from app.models.outcome import Outcome
from app.models.user import User


async def _fresh(db, model, *where):
    res = await db.execute(select(model).where(*where).execution_options(populate_existing=True))
    return res.scalar_one()


async def test_binary_price_moved_rejects_and_rolls_back(client, db, make_user, make_binary_market):
    trader = await make_user("trader_bin", points=10_000.0)
    whale = await make_user("whale_bin", points=100_000.0)
    m = await make_binary_market("pm-bin", b=100.0)

    # 1. Quote for the trader
    q = (await client.get(f"/api/markets/{m.id}/quote", params={"side": "YES", "amount": 100})).json()

    # 2. A whale moves the price hard
    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"side": "YES", "points": 5000},
        headers=auth_headers(whale),
    )
    assert resp.status_code == 200

    market_before = await _fresh(db, Market, Market.id == m.id)
    q_yes_before, q_no_before = market_before.q_yes, market_before.q_no

    # 3. Trader executes with the STALE quoted price → 409 PRICE_MOVED
    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"side": "YES", "points": 100, "quoted_avg_price": q["avg_fill_price"]},
        headers=auth_headers(trader),
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "PRICE_MOVED"
    assert detail["quoted_avg_price"] == q["avg_fill_price"]
    assert detail["current_avg_price"] > q["avg_fill_price"]

    # 4. Rollback clean: trader balance and market state untouched
    trader_after = await _fresh(db, User, User.id == trader.id)
    market_after = await _fresh(db, Market, Market.id == m.id)
    assert trader_after.points == 10_000.0
    assert market_after.q_yes == q_yes_before
    assert market_after.q_no == q_no_before


async def test_binary_fresh_quote_executes(client, make_user, make_binary_market):
    trader = await make_user("trader_fresh", points=10_000.0)
    m = await make_binary_market("pm-fresh", b=100.0)
    q = (await client.get(f"/api/markets/{m.id}/quote", params={"side": "NO", "amount": 100})).json()
    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"side": "NO", "points": 100, "quoted_avg_price": q["avg_fill_price"]},
        headers=auth_headers(trader),
    )
    assert resp.status_code == 200


async def test_binary_without_quoted_price_still_works(client, make_user, make_binary_market):
    """quoted_avg_price is optional — old clients keep working."""
    trader = await make_user("trader_legacy", points=10_000.0)
    m = await make_binary_market("pm-legacy", b=100.0)
    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"side": "YES", "points": 100},
        headers=auth_headers(trader),
    )
    assert resp.status_code == 200


async def test_binary_within_tolerance_executes(client, make_user, make_binary_market):
    """A tiny drift (≤1% relative) must NOT reject."""
    trader = await make_user("trader_tol", points=10_000.0)
    nudger = await make_user("nudger_tol", points=10_000.0)
    m = await make_binary_market("pm-tol", b=1000.0)  # deep book: tiny moves

    q = (await client.get(f"/api/markets/{m.id}/quote", params={"side": "YES", "amount": 100})).json()
    # Nudge the price a hair (deep book → far below 1% avg-fill drift)
    resp = await client.post(
        f"/api/markets/{m.id}/trade", json={"side": "YES", "points": 10}, headers=auth_headers(nudger)
    )
    assert resp.status_code == 200
    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"side": "YES", "points": 100, "quoted_avg_price": q["avg_fill_price"]},
        headers=auth_headers(trader),
    )
    assert resp.status_code == 200


async def test_multi_price_moved_rejects(client, db, make_user, make_multi_market):
    trader = await make_user("trader_multi", points=10_000.0)
    whale = await make_user("whale_multi", points=100_000.0)
    m = await make_multi_market("pm-multi", outcome_keys=("A", "B", "C"), b=100.0)

    q = (await client.get(f"/api/markets/{m.id}/quote", params={"outcome_key": "A", "amount": 100})).json()

    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"outcome_key": "A", "points": 5000},
        headers=auth_headers(whale),
    )
    assert resp.status_code == 200

    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"outcome_key": "A", "points": 100, "quoted_avg_price": q["avg_fill_price"]},
        headers=auth_headers(trader),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "PRICE_MOVED"

    # outcome state untouched by the rejected trade
    trader_after = await _fresh(db, User, User.id == trader.id)
    assert trader_after.points == 10_000.0


async def test_multi_fresh_quote_executes(client, make_user, make_multi_market):
    trader = await make_user("trader_multi_ok", points=10_000.0)
    m = await make_multi_market("pm-multi-ok", outcome_keys=("A", "B"), b=100.0)
    q = (await client.get(f"/api/markets/{m.id}/quote", params={"outcome_key": "B", "amount": 100})).json()
    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"outcome_key": "B", "points": 100, "quoted_avg_price": q["avg_fill_price"]},
        headers=auth_headers(trader),
    )
    assert resp.status_code == 200
