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


# ── cancelación ──────────────────────────────────────────────────────────────

async def test_cancel_reembolsa_lo_pagado(db, make_user, make_binary_market, make_multi_market):
    u = await make_user("cancelado", points=100)
    v = await make_user("otro", points=100)
    mid = (await make_binary_market("bin-cancel")).id  # id: el rollback de abajo expira el objeto
    db.add(Position(user_id=u.id, market_id=mid, outcome_key="YES", shares=40, avg_cost=0.35))
    db.add(Position(user_id=v.id, market_id=mid, outcome_key="NO", shares=10, avg_cost=0.6))
    await db.commit()

    r = await resolution.cancel(db, mid)
    assert r == {"ok": True, "resolution": "CANCELLED", "positions_refunded": 2, "refunded": 20.0}
    await db.refresh(u)
    await db.refresh(v)
    assert u.points == 114 and v.points == 106
    assert u.total_predictions == 0 and u.correct_predictions == 0  # no cuenta como acierto ni fallo
    m2 = (await db.execute(select(Market).where(Market.id == mid))).scalar_one()
    assert m2.status == MarketStatus.CANCELLED and m2.resolved_at is not None
    n_ledger = (await db.execute(select(func.count()).select_from(PointsLedger).where(PointsLedger.reason == "refund"))).scalar_one()
    assert n_ledger == 2
    shares = (await db.execute(select(func.sum(Position.shares)).where(Position.market_id == mid))).scalar_one()
    assert shares == 0
    # no se puede cancelar ni resolver dos veces
    with pytest.raises(resolution.ResolutionError) as ex:
        await resolution.cancel(db, mid)
    assert ex.value.code == "MARKET_ALREADY_RESOLVED"
    await db.rollback()
    with pytest.raises(resolution.ResolutionError):
        await resolution.resolve(db, mid, resolution="YES")
    await db.rollback()


async def _admin(make_user, db):
    admin = await make_user("admin")
    admin.email = "mdabahh@atid.edu.mx"
    await db.commit()
    return admin


async def test_endpoint_cancel(client, db, make_user, make_multi_market):
    admin = await _admin(make_user, db)
    otro = await make_user("otro")
    m = await make_multi_market("multi-cancel", outcome_keys=("local", "empate", "visitante"))
    db.add(Position(user_id=otro.id, market_id=m.id, outcome_key="empate", shares=10, avg_cost=0.3))
    await db.commit()
    r = await client.post(f"/api/admin/markets/{m.id}/cancel", headers=auth_headers(otro))
    assert r.status_code == 403
    r = await client.post(f"/api/admin/markets/{m.id}/cancel", headers=auth_headers(admin))
    assert r.status_code == 200 and r.json()["positions_refunded"] == 1 and r.json()["refunded"] == 3.0
    r = await client.post(f"/api/admin/markets/{m.id}/cancel", headers=auth_headers(admin))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "MARKET_ALREADY_RESOLVED"
    r = await client.post("/api/admin/markets/no-existe/cancel", headers=auth_headers(admin))
    assert r.status_code == 404


async def test_endpoint_patch_reabre_aplazado(client, db, make_user, make_multi_market):
    from datetime import datetime, timedelta, timezone
    from app.models.outcome import Outcome
    admin = await _admin(make_user, db)
    m = await make_multi_market("mls-aplazado", outcome_keys=("local", "empate", "visitante"))
    m.status = MarketStatus.PENDING_RESOLUTION
    m.ends_at = datetime.now(timezone.utc) - timedelta(days=7)
    m.closing_notified_at = datetime.now(timezone.utc)
    await db.commit()

    # reabrir sin fecha futura → 400
    r = await client.patch(f"/api/admin/markets/{m.id}", json={"status": "open"}, headers=auth_headers(admin))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "ENDS_AT_IN_PAST"
    # outcome_key desconocido → 400
    r = await client.patch(f"/api/admin/markets/{m.id}", json={"outcome_labels": {"nope": "x"}}, headers=auth_headers(admin))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "INVALID_OUTCOME_KEY"

    nueva = (datetime.now(timezone.utc) + timedelta(days=40)).replace(microsecond=0)
    body = {"status": "open", "ends_at": nueva.isoformat(), "question": "¿Quién ganará D.C. United vs. FC Cincinnati?",
            "rules": "Normas nuevas", "outcome_labels": {"local": "🏠 D.C. United", "visitante": "✈️ FC Cincinnati"}}
    r = await client.patch(f"/api/admin/markets/{m.id}", json=body, headers=auth_headers(admin))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "open" and set(r.json()["cambios"]) == {"ends_at", "status", "question", "rules", "outcome_labels"}
    fresh = (await db.execute(select(Market).where(Market.id == m.id).execution_options(populate_existing=True))).scalar_one()
    assert fresh.status == MarketStatus.OPEN and fresh.ends_at == nueva and fresh.closing_notified_at is None
    assert fresh.question.startswith("¿Quién ganará D.C. United") and fresh.rules == "Normas nuevas"
    labels = {o.outcome_key: o.label for o in (await db.execute(select(Outcome).where(Outcome.market_id == m.id))).scalars().all()}
    assert labels["local"] == "🏠 D.C. United" and labels["visitante"] == "✈️ FC Cincinnati" and labels["empate"] == "Opción empate"

    # resuelto → no editable
    await resolution.resolve(db, m.id, outcome_key="local")
    r = await client.patch(f"/api/admin/markets/{m.id}", json={"question": "x"}, headers=auth_headers(admin))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "MARKET_ALREADY_RESOLVED"
