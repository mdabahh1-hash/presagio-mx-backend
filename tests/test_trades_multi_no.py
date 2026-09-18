"""«No» de una opción en un mercado multi: NO_k paga 1 PT si gana cualquier
opción distinta de k (lmsr.trade_cost_multi_no)."""
import math

from sqlalchemy import select

from app.core import lmsr
from app.models.outcome import Outcome
from app.models.points_ledger import PointsLedger
from app.models.position import Position
from app.models.trade import Trade, TradeSide
from app.models.user import User
from app.services import resolution
from tests.conftest import auth_headers


async def _q(db, market_id) -> dict[str, float]:
    res = await db.execute(
        select(Outcome).where(Outcome.market_id == market_id).execution_options(populate_existing=True)
    )
    return {o.outcome_key: o.q for o in res.scalars().all()}


async def _set_prices(db, market_id, targets: dict[str, float], b: float) -> None:
    qs = lmsr.init_qs_for_targets(targets, b)
    prices = lmsr.prices_multi(qs, b)
    res = await db.execute(select(Outcome).where(Outcome.market_id == market_id))
    for o in res.scalars().all():
        o.q, o.price = qs[o.outcome_key], prices[o.outcome_key]
    await db.commit()


def test_matematica_no_cotas_e_identidad():
    q, b = {"A": 120.0, "B": -40.0, "C": 15.0}, 100.0
    p = lmsr.outcome_price(q, b, "A")
    for n in (0.5, 10.0, 300.0):
        c = lmsr.trade_cost_multi_no(q, b, "A", n)
        # Traslación: C(q + n·(1−e_k)) − C(q) = n + C(q − n·e_k) − C(q)
        q_menos = {**q, "A": q["A"] - n}
        assert math.isclose(c, n + lmsr.cost_multi(q_menos, b) - lmsr.cost_multi(q, b), rel_tol=1e-12)
        assert n * (1 - p) <= c <= n
    shares = lmsr.shares_for_cost_multi_no(q, b, "A", 50.0)
    assert math.isclose(lmsr.trade_cost_multi_no(q, b, "A", shares), 50.0, abs_tol=1e-6)


async def test_quote_y_compra_no_de_una_opcion(client, db, make_user, make_multi_market):
    user = await make_user("comprador", points=1_000.0)
    m = await make_multi_market("mno-1", b=100.0)
    q0 = await _q(db, m.id)
    p0 = lmsr.outcome_price(q0, m.b, "A")

    r = await client.get(f"/api/markets/{m.id}/quote", params={"outcome_key": "A", "side": "NO", "amount": 50})
    assert r.status_code == 200, r.text
    quote = r.json()
    assert quote["side"] == "NO" and quote["outcome_key"] == "A"
    assert math.isclose(quote["mid_price"], round((1 - p0) * 100, 2))
    assert math.isclose(quote["mid_yes_price"], round(p0 * 100, 2))

    r = await client.post(
        f"/api/markets/{m.id}/trade",
        json={"outcome_key": "A", "side": "NO", "points": 50, "quoted_avg_price": quote["avg_fill_price"]},
        headers=auth_headers(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["side"] == "NO" and body["outcome_key"] == "A"
    assert math.isclose(body["cost"], 50.0, abs_tol=1e-4)
    assert 50.0 <= body["shares"] <= 50.0 / (1 - p0)
    # Escala Sí de la opción, como el binario: el Sí de A baja.
    assert body["price_after"] < body["price_before"]

    q1 = await _q(db, m.id)
    assert q1["A"] == q0["A"] and q1["B"] > q0["B"] and q1["C"] > q0["C"]
    assert lmsr.outcome_price(q1, m.b, "A") < p0

    pos = (await db.execute(select(Position).where(Position.user_id == user.id))).scalar_one()
    assert pos.side == TradeSide.NO and pos.outcome_key == "A"
    trade = (await db.execute(select(Trade).where(Trade.user_id == user.id))).scalar_one()
    assert trade.side == TradeSide.NO
    u = (await db.execute(select(User).where(User.id == user.id).execution_options(populate_existing=True))).scalar_one()
    assert math.isclose(u.points, 950.0, abs_tol=1e-4)
    ledger = (await db.execute(select(PointsLedger).where(PointsLedger.user_id == user.id))).scalars().all()
    assert [round(x.delta, 4) for x in ledger] == [-50.0]


async def test_si_y_no_de_la_misma_opcion_coexisten(client, db, make_user, make_multi_market):
    user = await make_user("ambos", points=1_000.0)
    m = await make_multi_market("mno-2", b=100.0)
    h = auth_headers(user)
    for payload in ({"outcome_key": "A", "points": 20}, {"outcome_key": "A", "side": "NO", "points": 20},
                    {"outcome_key": "A", "side": "NO", "points": 20}):
        r = await client.post(f"/api/markets/{m.id}/trade", json=payload, headers=h)
        assert r.status_code == 200, r.text
    rows = (await db.execute(select(Position).where(Position.user_id == user.id))).scalars().all()
    assert {(p.outcome_key, p.side) for p in rows} == {("A", None), ("A", TradeSide.NO)} and len(rows) == 2


async def test_validaciones(client, db, make_user, make_multi_market, make_binary_market):
    user = await make_user("val", points=1_000.0)
    mm = await make_multi_market("mno-3")
    mb = await make_binary_market("mno-bin")
    h = auth_headers(user)
    r = await client.post(f"/api/markets/{mm.id}/trade", json={"outcome_key": "A", "side": "YES", "points": 20}, headers=h)
    assert r.status_code == 422
    r = await client.get(f"/api/markets/{mm.id}/quote", params={"outcome_key": "A", "side": "YES", "amount": 20})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "SIDE_NOT_ALLOWED"
    r = await client.post(f"/api/markets/{mb.id}/trade", json={"outcome_key": "YES", "side": "NO", "points": 20}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "OUTCOME_KEY_NOT_ALLOWED"


async def test_resolucion_no_gana_si_gana_otra_y_pierde_si_gana_k(db, make_user, make_multi_market):
    a = await make_user("no_a", points=0.0)
    b = await make_user("si_a", points=0.0)
    m = await make_multi_market("mno-4")
    db.add(Position(user_id=a.id, market_id=m.id, outcome_key="A", side=TradeSide.NO, shares=10, avg_cost=0.6))
    db.add(Position(user_id=b.id, market_id=m.id, outcome_key="A", side=None, shares=7, avg_cost=0.4))
    await db.commit()
    await resolution.resolve(db, m.id, outcome_key="B")
    pts = {u.username: u.points for u in (await db.execute(
        select(User).execution_options(populate_existing=True))).scalars().all()}
    assert pts == {"no_a": 10.0, "si_a": 0.0}

    c = await make_user("no_c", points=0.0)
    m2 = await make_multi_market("mno-5")
    db.add(Position(user_id=c.id, market_id=m2.id, outcome_key="A", side=TradeSide.NO, shares=10, avg_cost=0.6))
    await db.commit()
    await resolution.resolve(db, m2.id, outcome_key="A")
    u = (await db.execute(select(User).where(User.id == c.id).execution_options(populate_existing=True))).scalar_one()
    assert u.points == 0.0 and u.total_predictions == 1 and u.correct_predictions == 0


async def test_portafolio_marca_no_con_complemento(client, db, make_user, make_multi_market):
    user = await make_user("porta", points=0.0)
    m = await make_multi_market("mno-6", b=100.0)
    await _set_prices(db, m.id, {"A": 80.0, "B": 10.0, "C": 10.0}, m.b)
    db.add(Position(user_id=user.id, market_id=m.id, outcome_key="A", side=TradeSide.NO, shares=100, avg_cost=0.2))
    await db.commit()
    r = await client.get("/api/users/me/positions", headers=auth_headers(user))
    assert r.status_code == 200, r.text
    [p] = r.json()
    assert p["side"] == "NO"
    assert math.isclose(p["current_price"], 0.20, abs_tol=1e-3)
    assert math.isclose(p["current_value"], 20.0, abs_tol=0.1)


async def test_historial_separa_si_y_no_de_la_misma_opcion(client, db, make_user, make_multi_market):
    user = await make_user("histo", points=1_000.0)
    m = await make_multi_market("mno-7")
    h = auth_headers(user)
    for payload in ({"outcome_key": "A", "points": 20}, {"outcome_key": "A", "side": "NO", "points": 30}):
        assert (await client.post(f"/api/markets/{m.id}/trade", json=payload, headers=h)).status_code == 200
    await resolution.resolve(db, m.id, outcome_key="C")
    r = await client.get("/api/users/me/history", headers=h)
    assert r.status_code == 200, r.text
    res = {(e["side"], e["type"]) for e in r.json() if e["type"] in ("win", "loss")}
    assert res == {(None, "loss"), ("NO", "win")}


def test_posicion_gana():
    assert lmsr.posicion_gana("NO", "A", "B", multi=True)
    assert not lmsr.posicion_gana("NO", "A", "A", multi=True)
    assert lmsr.posicion_gana(None, "A", "A", multi=True)
    assert lmsr.posicion_gana("NO", "NO", "NO", multi=False)
    assert not lmsr.posicion_gana("YES", "YES", "NO", multi=False)
    assert lmsr.posicion_gana("YES", None, "YES", multi=False)


async def test_backfill_ledger_paga_no_de_multi(client, db, make_user, make_multi_market):
    from app.services.ledger_backfill import backfill_ledger
    from app.models.market import Market, MarketStatus
    from datetime import datetime, timezone
    from sqlalchemy import delete

    user = await make_user("backfill", points=0.0)
    m = await make_multi_market("mno-8")
    db.add(Trade(user_id=user.id, market_id=m.id, side=TradeSide.NO, outcome_key="A", shares=12, cost=8, price_before=33, price_after=30))
    db.add(Trade(user_id=user.id, market_id=m.id, side=None, outcome_key="A", shares=5, cost=2, price_before=30, price_after=31))
    mk = (await db.execute(select(Market).where(Market.id == m.id))).scalar_one()
    mk.status, mk.resolved_outcome_key, mk.resolved_at = MarketStatus.RESOLVED, "B", datetime.now(timezone.utc)
    await db.execute(delete(PointsLedger))
    await db.commit()
    await backfill_ledger()
    rows = (await db.execute(select(PointsLedger.reason, PointsLedger.delta).where(PointsLedger.user_id == user.id))).all()
    assert sorted(rows) == [("payout", 12.0), ("trade", -8.0), ("trade", -2.0)]


async def test_binario_si_y_no_mismo_usuario_sin_cambio(client, db, make_user, make_binary_market):
    """Comportamiento previo al índice por lado: en binario, Sí y No del mismo
    usuario son dos filas (outcome_key = lado) y cada compra se acumula en la suya
    con costo promedio ponderado; nunca se compensan entre sí."""
    user = await make_user("binario", points=1_000.0)
    m = await make_binary_market("mno-bin-2", b=100.0)
    h = auth_headers(user)
    compras = []
    for side, pts in (("YES", 20), ("NO", 30), ("YES", 40)):
        r = await client.post(f"/api/markets/{m.id}/trade", json={"side": side, "points": pts}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["outcome_key"] == side and body["side"] == side
        compras.append((side, body["shares"], body["cost"]))

    rows = (await db.execute(
        select(Position).where(Position.user_id == user.id).execution_options(populate_existing=True)
    )).scalars().all()
    by_key = {(p.outcome_key, p.side): p for p in rows}
    assert set(by_key) == {("YES", TradeSide.YES), ("NO", TradeSide.NO)} and len(rows) == 2

    yes = by_key[("YES", TradeSide.YES)]
    si = [(s, c) for side, s, c in compras if side == "YES"]
    assert math.isclose(yes.shares, sum(s for s, _ in si), rel_tol=1e-9)
    assert math.isclose(yes.avg_cost, sum(c for _, c in si) / yes.shares, rel_tol=1e-9)
    no = by_key[("NO", TradeSide.NO)]
    assert math.isclose(no.shares, compras[1][1], rel_tol=1e-9)
    assert math.isclose(no.avg_cost, compras[1][2] / compras[1][1], rel_tol=1e-9)
