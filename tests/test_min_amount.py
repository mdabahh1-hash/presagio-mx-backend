"""Apuesta mínima (MIN_TRADE_POINTS = 10): trade y quote rechazan con MIN_AMOUNT."""
from tests.conftest import auth_headers


async def test_trade_below_min_rejected(client, make_user, make_binary_market):
    user = await make_user("min_trader", points=10_000.0)
    m = await make_binary_market("min-bin", b=3000.0)

    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"side": "YES", "points": 5},
        headers=auth_headers(user),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "MIN_AMOUNT"

    resp = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"side": "YES", "points": 10},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200


async def test_quote_below_min_rejected(client, make_binary_market):
    m = await make_binary_market("min-quote", b=3000.0)
    resp = await client.get(f"/api/markets/{m.id}/quote", params={"side": "YES", "amount": 5})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "MIN_AMOUNT"

    resp = await client.get(f"/api/markets/{m.id}/quote", params={"side": "YES", "amount": 10})
    assert resp.status_code == 200
