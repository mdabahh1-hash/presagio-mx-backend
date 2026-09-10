"""app/services/resolution.resolve: liquidación compartida por el endpoint admin
y el plan nocturno."""
import pytest
from sqlalchemy import select, func

from app.models.points_ledger import PointsLedger
from app.models.position import Position
from app.models.market import Market, MarketStatus
from app.services import resolution
from tests.conftest import auth_headers


async def _posicion(db, user, market_id, outcome_key, shares, side=None):
    db.add(Position(user_id=user.id, market_id=market_id, outcome_key=outcome_key, shares=shares, avg_cost=0.5, side=side))
    await db.commit()


async def test_binario_yes_paga_solo_al_lado_ganador(db, make_user, make_binary_market):
    ganador = await make_user("gana", points=1000)
    perdedor = await make_user("pierde", points=1000)
    m = await make_binary_market("bin-1")
    await _posicion(db, ganador, m.id, "YES", 40)
    await _posicion(db, perdedor, m.id, "NO", 25)

    r = await resolution.resolve(db, m.id, resolution="yes")
    assert r == {"ok": True, "resolution": "YES", "positions_settled": 2}

    await db.refresh(ganador)
    await db.refresh(perdedor)
    assert ganador.points == 1040 and ganador.correct_predictions == 1
    assert perdedor.points == 1000 and perdedor.total_predictions == 1
    m2 = (await db.execute(select(Market).where(Market.id == m.id))).scalar_one()
    assert m2.status == MarketStatus.RESOLVED_YES and m2.resolved_at is not None
    n_ledger = (await db.execute(select(func.count()).select_from(PointsLedger).where(PointsLedger.reason == "payout"))).scalar_one()
    assert n_ledger == 1  # el payout 0 no escribe fila
    shares = (await db.execute(select(func.sum(Position.shares)).where(Position.market_id == m.id))).scalar_one()
    assert shares == 0


async def test_multi_paga_outcome_ganador(db, make_user, make_multi_market):
    u = await make_user("multi", points=500)
    m = await make_multi_market("multi-1", outcome_keys=("local", "empate", "visitante"))
    await _posicion(db, u, m.id, "empate", 10)
    await _posicion(db, u, m.id, "local", 7)
    r = await resolution.resolve(db, m.id, outcome_key="empate")
    assert r["resolution"] == "empate" and r["positions_settled"] == 2
    await db.refresh(u)
    assert u.points == 510
    m2 = (await db.execute(select(Market).where(Market.id == m.id))).scalar_one()
    assert m2.status == MarketStatus.RESOLVED and m2.resolved_outcome_key == "empate"


async def test_errores_de_dominio(db, make_binary_market, make_multi_market):
    mid = (await make_binary_market("bin-2")).id
    mmid = (await make_multi_market("multi-2", outcome_keys=("a", "b"))).id  # ids: el rollback expira los objetos
    with pytest.raises(resolution.ResolutionError) as ex:
        await resolution.resolve(db, "no-existe", resolution="YES")
    assert ex.value.code == "MARKET_NOT_FOUND" and ex.value.status == 404
    await db.rollback()
    with pytest.raises(resolution.ResolutionError) as ex:
        await resolution.resolve(db, mid, resolution="MAYBE")
    assert ex.value.code == "INVALID_RESOLUTION"
    await db.rollback()
    with pytest.raises(resolution.ResolutionError) as ex:
        await resolution.resolve(db, mid)
    assert ex.value.code == "RESOLUTION_REQUIRED"
    await db.rollback()
    with pytest.raises(resolution.ResolutionError) as ex:
        await resolution.resolve(db, mmid, outcome_key="zzz")
    assert ex.value.code == "INVALID_OUTCOME_KEY"
    await db.rollback()
    await resolution.resolve(db, mid, resolution="NO")
    with pytest.raises(resolution.ResolutionError) as ex:
        await resolution.resolve(db, mid, resolution="NO")
    assert ex.value.code == "MARKET_ALREADY_RESOLVED"


async def test_endpoint_admin_traduce_errores(client, db, make_user, make_binary_market):
    admin = await make_user("admin")
    admin.email = "mdabahh@atid.edu.mx"
    await db.commit()
    m = await make_binary_market("bin-3")
    r = await client.post(f"/api/admin/markets/{m.id}/resolve", json={"resolution": "YES"}, headers=auth_headers(admin))
    assert r.status_code == 200 and r.json()["ok"] is True
    r = await client.post(f"/api/admin/markets/{m.id}/resolve", json={"resolution": "YES"}, headers=auth_headers(admin))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "MARKET_ALREADY_RESOLVED"
    r = await client.post("/api/admin/markets/nope/resolve", json={"resolution": "YES"}, headers=auth_headers(admin))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MARKET_NOT_FOUND"
