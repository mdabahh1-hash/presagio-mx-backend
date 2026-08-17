"""Characterization (golden) tests for the BINARY trade execution path.

These freeze the EXACT current behavior of POST /markets/{id}/trade before any
refactor of app/api/trades.py. The GOLDEN values below were captured against
the pre-refactor code; a refactor of the binary path must keep every value
bit-identical (compared with ==, no tolerance). If any value changes, STOP and
investigate — the money path semantics moved.

Scenarios: {balanced 50/50, skewed 24%} × {YES, NO} × {10 PT, 1000 PT}.
Captured per scenario: response shares/cost/price_before/price_after/
new_yes_price/new_balance, and post-trade market q_yes/q_no + yes_price +
volume from the DB.

To (re)capture goldens: CAPTURE_GOLDEN=1 pytest tests/test_trade_semantics.py -s
which prints a ready-to-paste GOLDEN dict and fails the run on purpose.
"""
import os

import pytest
from sqlalchemy import select

from tests.conftest import auth_headers
from app.models.market import Market

CAPTURE = os.environ.get("CAPTURE_GOLDEN") == "1"

USER_POINTS = 100_000.0

# (scenario_key) -> (initial_yes or None for balanced, side, points)
SCENARIOS = {
    "balanced-YES-10": (None, "YES", 10),
    "balanced-YES-1000": (None, "YES", 1000),
    "balanced-NO-10": (None, "NO", 10),
    "balanced-NO-1000": (None, "NO", 1000),
    "skewed24-YES-10": (0.24, "YES", 10),
    "skewed24-YES-1000": (0.24, "YES", 1000),
    "skewed24-NO-10": (0.24, "NO", 10),
    "skewed24-NO-1000": (0.24, "NO", 1000),
}

GOLDEN: dict[str, dict] = {
    "balanced-YES-10": {
        "shares": 19.09028289373964,
        "cost": 10.000000000603137,
        "price_before": 50.0,
        "price_after": 54.76,
        "new_yes_price": 54.76,
        "new_balance": 99989.9999999994,
        "q_yes": 19.09028289373964,
        "q_no": 0.0,
        "market_yes_price": 54.76,
        "market_volume": 10.000000000603137,
    },
    "balanced-YES-1000": {
        "shares": 1069.3124480337701,
        "cost": 1000.0000000000286,
        "price_before": 50.0,
        "price_after": 100.0,
        "new_yes_price": 100.0,
        "new_balance": 98999.99999999997,
        "q_yes": 1069.3124480337701,
        "q_no": 0.0,
        "market_yes_price": 100.0,
        "market_volume": 1000.0000000000286,
    },
    "balanced-NO-10": {
        "shares": 19.09028289373964,
        "cost": 10.000000000603137,
        "price_before": 50.0,
        "price_after": 45.24,
        "new_yes_price": 45.24,
        "new_balance": 99989.9999999994,
        "q_yes": 0.0,
        "q_no": 19.09028289373964,
        "market_yes_price": 45.24,
        "market_volume": 10.000000000603137,
    },
    "balanced-NO-1000": {
        "shares": 1069.3124480337701,
        "cost": 1000.0000000000286,
        "price_before": 50.0,
        "price_after": 0.0,
        "new_yes_price": 0.0,
        "new_balance": 98999.99999999997,
        "q_yes": 0.0,
        "q_no": 1069.3124480337701,
        "market_yes_price": 0.0,
        "market_volume": 1000.0000000000286,
    },
    "skewed24-YES-10": {
        "shares": 36.34007857181132,
        "cost": 9.99999999981495,
        "price_before": 24.0,
        "price_after": 31.23,
        "new_yes_price": 31.23,
        "new_balance": 99990.00000000019,
        "q_yes": -78.92787242202724,
        "q_no": 0.0,
        "market_yes_price": 31.23,
        "market_volume": 9.99999999981495,
    },
    "skewed24-YES-1000": {
        "shares": 1142.7081851093135,
        "cost": 999.9999999994885,
        "price_before": 24.0,
        "price_after": 100.0,
        "new_yes_price": 100.0,
        "new_balance": 99000.00000000051,
        "q_yes": 1027.440234115475,
        "q_no": 0.0,
        "market_yes_price": 100.0,
        "market_volume": 999.9999999994885,
    },
    "skewed24-NO-10": {
        "shares": 12.96086472866591,
        "cost": 10.000000000240671,
        "price_before": 24.0,
        "price_after": 21.72,
        "new_yes_price": 21.72,
        "new_balance": 99989.99999999975,
        "q_yes": -115.26795099383855,
        "q_no": 12.96086472866591,
        "market_yes_price": 21.72,
        "market_volume": 10.000000000240671,
    },
    "skewed24-NO-1000": {
        "shares": 1027.4425949660326,
        "cost": 1000.000000000107,
        "price_before": 24.0,
        "price_after": 0.0,
        "new_yes_price": 0.0,
        "new_balance": 98999.9999999999,
        "q_yes": -115.26795099383855,
        "q_no": 1027.4425949660326,
        "market_yes_price": 0.0,
        "market_volume": 1000.000000000107,
    },
}


async def _run_scenario(client, make_user, make_binary_market, db, key: str) -> dict:
    initial_yes, side, points = SCENARIOS[key]
    user = await make_user(username=f"u_{key.replace('-', '_').lower()}", points=USER_POINTS)
    market = await make_binary_market(f"mkt-{key.lower()}", b=100.0, initial_yes=initial_yes)

    resp = await client.post(
        f"/api/markets/{market.id}/trade",
        json={"side": side, "points": points},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # populate_existing: the fixture session already holds this Market in its
    # identity map with pre-trade values; force a re-read of the committed row.
    res = await db.execute(
        select(Market).where(Market.id == market.id).execution_options(populate_existing=True)
    )
    m = res.scalar_one()

    return {
        "shares": body["shares"],
        "cost": body["cost"],
        "price_before": body["price_before"],
        "price_after": body["price_after"],
        "new_yes_price": body["new_yes_price"],
        "new_balance": body["new_balance"],
        "q_yes": m.q_yes,
        "q_no": m.q_no,
        "market_yes_price": m.yes_price,
        "market_volume": m.volume,
    }


@pytest.mark.parametrize("key", list(SCENARIOS))
async def test_binary_trade_golden(client, make_user, make_binary_market, db, key):
    actual = await _run_scenario(client, make_user, make_binary_market, db, key)

    if CAPTURE:
        print(f'\n    "{key}": {{')
        for k, v in actual.items():
            print(f'        "{k}": {v!r},')
        print("    },")
        pytest.fail("CAPTURE_GOLDEN mode: values printed above; paste into GOLDEN and rerun.")

    assert key in GOLDEN, f"No golden values for {key} — run with CAPTURE_GOLDEN=1"
    expected = GOLDEN[key]
    for field, exp in expected.items():
        got = actual[field]
        assert got == exp, (
            f"{key}.{field}: golden={exp!r} actual={got!r} — "
            "binary trade semantics CHANGED; stop and investigate."
        )
