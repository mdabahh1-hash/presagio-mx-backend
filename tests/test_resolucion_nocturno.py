"""Plan nocturno: armado (con armar_plan simulado, sin red), correo, token de
aprobación de un solo uso y aplicación."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.market import Market, MarketStatus
from app.models.position import Position
from app.models.resolution_plan import ResolutionPlan
from app.services.resolucion import nocturno
from app.services import email as email_mod
from tests.conftest import auth_headers


@pytest.fixture
def correos(monkeypatch):
    enviados: list[tuple[str, str]] = []

    async def fake_send(to, subject, html):
        enviados.append((subject, html))

    monkeypatch.setattr(email_mod, "_send", fake_send)
    return enviados


def _plan_falso(mercados: list[dict]) -> dict:
    """Sustituto de armar_plan: resuelve todos los multi como 'local' con doble
    fuente y escala los binarios."""
    res, esc = [], []
    for m in mercados:
        base = {"id": m["id"], "pregunta": m["question"], "liga": m.get("subcategory"), "volume": m["volume"], "num_trades": m["num_trades"]}
        if m["market_type"] == "multi":
            res.append({**base, "veredicto": "local", "resultado": "A 1-0 B", "fuente_1": "https://www.espn.com/x",
                        "fuente_2": "https://www.thesportsdb.com/event/1", "confianza": "alta"})
        else:
            esc.append({**base, "razon": "accesorio", "veredicto_sugerido": "YES", "fuente_1": "https://www.espn.com/y"})
    return {"generado": "x", "modo": "test", "resoluciones": res, "escalados": esc}


async def _vencer(db, *markets):
    for m in markets:
        m.status = MarketStatus.PENDING_RESOLUTION
        m.ends_at = datetime.now(timezone.utc) - timedelta(hours=3)
    await db.commit()


@pytest.fixture
def armado(monkeypatch):
    monkeypatch.setattr(nocturno, "armar_plan", _plan_falso)


async def test_sin_pendientes_no_crea_plan(db, correos, armado):
    assert await nocturno.correr_plan_nocturno() is None
    assert correos == []


async def test_crea_plan_y_manda_correo(db, correos, armado, make_multi_market, make_binary_market):
    m1 = await make_multi_market("p-1", outcome_keys=("local", "empate", "visitante"))
    b1 = await make_binary_market("p-bin")
    await _vencer(db, m1, b1)

    row = await nocturno.correr_plan_nocturno()
    assert row is not None and row.status == "pending"
    assert row.resumen == {"resoluciones": 1, "escalados": 1, "con_operaciones": 0, "volumen": 0, "sugeridos": 1}
    # spawn() manda el correo en una task: cederle el loop
    import asyncio
    await asyncio.sleep(0)
    assert len(correos) == 1
    subject, html = correos[0]
    assert "1 mercados listos" in subject
    assert f"/api/admin/resolucion/planes/{row.id}/aprobar?t=" in html
    assert "p-bin" in html and "sugerido" in html

    # idempotencia: hoy ya hay plan
    assert await nocturno.correr_plan_nocturno() is None
    # forzar sí arma otro
    row2 = await nocturno.correr_plan_nocturno(forzar=True)
    assert row2 is not None and row2.id != row.id


async def test_token_invalido_y_get_no_ejecuta(client, db, armado, correos, make_multi_market):
    m1 = await make_multi_market("p-2", outcome_keys=("local", "empate", "visitante"))
    await _vencer(db, m1)
    row = await nocturno.correr_plan_nocturno()
    url = nocturno.url_aprobacion(row)
    path = url.split("/api", 1)[1]
    assert path.startswith("/admin/resolucion/planes/")

    r = await client.get("/api" + path)
    assert r.status_code == 200 and "Confirmar y resolver 1 mercados" in r.text
    m = (await db.execute(select(Market).where(Market.id == "p-2").execution_options(populate_existing=True))).scalar_one()
    assert m.status == MarketStatus.PENDING_RESOLUTION  # el GET no resuelve

    r = await client.get(f"/api/admin/resolucion/planes/{row.id}/aprobar?t=basura")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "INVALID_PLAN_TOKEN"
    otro = nocturno.make_plan_token(row.id, "nonce-equivocado")
    r = await client.post(f"/api/admin/resolucion/planes/{row.id}/aprobar?t={otro}")
    assert r.status_code == 400
    r = await client.get(f"/api/admin/resolucion/planes/{row.id}/aprobar")
    assert r.status_code == 400


async def test_post_aplica_una_sola_vez(client, db, armado, correos, make_user, make_multi_market):
    u = await make_user("apostador", points=100)
    m1 = await make_multi_market("p-3", outcome_keys=("local", "empate", "visitante"))
    m2 = await make_multi_market("p-4", outcome_keys=("local", "empate", "visitante"))
    db.add(Position(user_id=u.id, market_id=m1.id, outcome_key="local", shares=12, avg_cost=0.5))
    await db.commit()
    await _vencer(db, m1, m2)
    row = await nocturno.correr_plan_nocturno()
    # p-4 se resolvió a mano antes de aprobar → debe saltarse
    m2.status = MarketStatus.RESOLVED
    await db.commit()

    t = nocturno.make_plan_token(row.id, row.nonce)
    r = await client.post(f"/api/admin/resolucion/planes/{row.id}/aprobar?t={t}")
    assert r.status_code == 200 and "Plan #" in r.text and "aplicado" in r.text

    fresh = (await db.execute(select(ResolutionPlan).where(ResolutionPlan.id == row.id))).scalar_one()
    assert fresh.status == "applied" and fresh.applied_at is not None
    assert [x["id"] for x in fresh.resultado["resueltos"]] == ["p-3"]
    assert [x["id"] for x in fresh.resultado["saltados"]] == ["p-4"]
    assert fresh.resultado["posiciones_liquidadas"] == 1
    await db.refresh(u)
    assert u.points == 112
    m1f = (await db.execute(select(Market).where(Market.id == "p-3").execution_options(populate_existing=True))).scalar_one()
    assert m1f.status == MarketStatus.RESOLVED and m1f.resolved_outcome_key == "local"

    # segundo clic: no vuelve a aplicar
    r = await client.post(f"/api/admin/resolucion/planes/{row.id}/aprobar?t={t}")
    assert r.status_code == 200 and "ya" in r.text.lower()
    r = await client.get(f"/api/admin/resolucion/planes/{row.id}/aprobar?t={t}")
    assert "applied" in r.text


async def test_plan_expirado_no_se_aplica(client, db, armado, correos, make_multi_market):
    m1 = await make_multi_market("p-5", outcome_keys=("local", "empate", "visitante"))
    await _vencer(db, m1)
    row = await nocturno.correr_plan_nocturno()
    viejo = (await db.execute(select(ResolutionPlan).where(ResolutionPlan.id == row.id))).scalar_one()
    viejo.created_at = datetime.now(timezone.utc) - timedelta(hours=100)
    await db.commit()
    # una corrida nueva expira el viejo y arma otro (no hay plan "de hoy")
    row2 = await nocturno.correr_plan_nocturno()
    assert row2 is not None and row2.id != row.id
    await db.refresh(viejo)
    assert viejo.status == "expired"
    t = nocturno.make_plan_token(row.id, viejo.nonce)
    r = await client.post(f"/api/admin/resolucion/planes/{row.id}/aprobar?t={t}")
    assert r.status_code == 200 and "expired" in r.text
    m = (await db.execute(select(Market).where(Market.id == "p-5").execution_options(populate_existing=True))).scalar_one()
    assert m.status == MarketStatus.PENDING_RESOLUTION


async def test_endpoints_admin_listar_y_disparar(client, db, make_user, armado, correos, monkeypatch):
    admin = await make_user("admin")
    admin.email = "mdabahh@atid.edu.mx"
    await db.commit()
    otro = await make_user("otro")
    r = await client.get("/api/admin/resolucion/planes", headers=auth_headers(otro))
    assert r.status_code == 403
    r = await client.get("/api/admin/resolucion/planes", headers=auth_headers(admin))
    assert r.status_code == 200 and r.json()["planes"] == []
    r = await client.post("/api/admin/resolucion/planes", headers=auth_headers(admin))
    assert r.status_code == 202 and r.json() == {"started": True}


def test_segundos_hasta_proxima_corrida():
    ahora = datetime(2026, 9, 10, 11, 30, tzinfo=timezone.utc)
    assert nocturno.segundos_hasta_proxima_corrida(ahora, hora_utc=12) == 1800
    ahora = datetime(2026, 9, 10, 12, 0, 30, tzinfo=timezone.utc)
    assert nocturno.segundos_hasta_proxima_corrida(ahora, hora_utc=12) == 86400 - 30
