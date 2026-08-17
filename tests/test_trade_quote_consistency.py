"""Quote → immediate trade of the same amount must match: same math path."""
import pytest

from tests.conftest import auth_headers


async def test_binary_trade_matches_quote(client, make_user, make_binary_market):
    user = await make_user("consistency_bin", points=10_000.0)
    m = await make_binary_market("cons-bin", b=100.0, initial_yes=0.24)

    q = (await client.get(f"/api/markets/{m.id}/quote", params={"side": "YES", "amount": 250})).json()
    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"side": "YES", "points": 250, "quoted_avg_price": q["avg_fill_price"]},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    t = resp.json()

    assert t["shares"] == pytest.approx(q["shares"], rel=1e-6)
    assert t["cost"] == pytest.approx(q["max_loss"], rel=1e-6)
    avg_fill_real = t["cost"] / t["shares"] * 100
    assert avg_fill_real == pytest.approx(q["avg_fill_price"], abs=0.01)
    # price_after in the trade is the 2dp cached YES pct; quote's is the YES-side spot too
    assert t["price_after"] == pytest.approx(q["price_after"], abs=0.01)


async def test_multi_trade_matches_quote(client, make_user, make_multi_market):
    user = await make_user("consistency_multi", points=10_000.0)
    m = await make_multi_market("cons-multi", outcome_keys=("A", "B", "C"), b=100.0)

    q = (await client.get(f"/api/markets/{m.id}/quote", params={"outcome_key": "A", "amount": 250})).json()
    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"outcome_key": "A", "points": 250, "quoted_avg_price": q["avg_fill_price"]},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    t = resp.json()

    assert t["shares"] == pytest.approx(q["shares"], rel=1e-6)
    assert t["cost"] == pytest.approx(q["max_loss"], rel=1e-6)
    # multi price_after: trade stores the outcome price (4dp via prices_multi)
    assert t["price_after"] == pytest.approx(q["price_after"], abs=0.01)
