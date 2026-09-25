"""Leaderboard mensual: ganancia por trade del mes, elegibilidad, cierre y aprobación."""
import math
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core import lmsr
from app.core.auth import ADMIN_EMAIL
from app.models.leaderboard_mes import LeaderboardMes, LeaderboardMesFila
from app.models.market import MarketStatus
from app.models.trade import Trade, TradeSide
from app.services import leaderboard_mensual as lb
from app.services.resolucion.nocturno import make_plan_token
from tests.conftest import auth_headers

OCT = date(2026, 10, 1)
EN_OCT = datetime(2026, 10, 15, 18, tzinfo=timezone.utc)


def _trade(db, user, market, cost, shares, side=TradeSide.YES, outcome_key=None, at=EN_OCT):
    db.add(Trade(user_id=user.id, market_id=market.id, side=side, outcome_key=outcome_key,
                 shares=shares, cost=cost, price_before=0.5, price_after=0.5, created_at=at))


def test_limites_del_mes_en_cdmx():
    a, b = lb.limites(OCT)
    assert a == datetime(2026, 10, 1, 6, tzinfo=timezone.utc)   # 00:00 CDMX (UTC−6)
    assert b == datetime(2026, 11, 1, 6, tzinfo=timezone.utc)
    assert lb.mes_de(datetime(2026, 11, 1, 5, 59, tzinfo=timezone.utc)) == OCT
    assert lb.limites(date(2026, 12, 1))[1] == datetime(2027, 1, 1, 6, tzinfo=timezone.utc)


async def test_valor_por_trade(db, make_user, make_binary_market, make_multi_market):
    u = await make_user("ana")
    gana, pierde, abierto, cancelado = [await make_binary_market(f"b{i}") for i in range(4)]
    alto = await make_binary_market("alto", initial_yes=0.9)
    multi = await make_multi_market("m1")
    gana.status, pierde.status, cancelado.status = MarketStatus.RESOLVED_YES, MarketStatus.RESOLVED_NO, MarketStatus.CANCELLED
    multi.status, multi.resolved_outcome_key = MarketStatus.RESOLVED, "B"
    _trade(db, u, gana, 50, 100)                                          # +50
    _trade(db, u, pierde, 50, 100)                                        # −50
    _trade(db, u, abierto, 50, 100)                                       # 100 × 0.5 − 50 = 0
    _trade(db, u, cancelado, 50, 100)                                     # 0
    _trade(db, u, alto, 50, 100)                                          # marca 90 > costo: topado, 0
    _trade(db, u, multi, 30, 60, side=TradeSide.NO, outcome_key="A")      # No de A, ganó B: +30
    _trade(db, u, gana, 999, 1, at=EN_OCT - timedelta(days=30))            # septiembre: no cuenta
    await db.commit()

    [f] = await lb.ranking_mes(db, OCT)
    assert math.isclose(f.ganancia, 30.0, abs_tol=1e-6)
    assert f.volumen == 280 and f.n_trades == 6 and f.n_mercados == 6
    assert math.isclose(lmsr.yes_price(abierto.q_yes, abierto.q_no, abierto.b), 0.5)


async def test_elegibilidad_y_empates(db, make_user, make_binary_market):
    ms = [await make_binary_market(f"e{i}") for i in range(5)]
    for m in ms:
        m.status = MarketStatus.RESOLVED_YES
    a, b, c, poco = [await make_user(n) for n in ("a", "b", "c", "poco")]
    admin = await make_user("admin")
    admin.email = ADMIN_EMAIL
    for u, gana in ((a, 10), (b, 10), (c, 5), (admin, 99)):
        for i in range(10):
            _trade(db, u, ms[i % 5], 10, 10 + gana / 10)   # ganancia = gana PT
    for i in range(20):
        _trade(db, poco, ms[0], 10, 1000)               # gana mucho, pero en un solo mercado
    await db.commit()

    filas = {f.user.username: f for f in await lb.ranking_mes(db, OCT)}
    assert (filas["a"].rank, filas["b"].rank, filas["c"].rank) == (1, 1, 3)
    assert filas["admin"].rank is None and not filas["admin"].elegible
    assert filas["poco"].rank is None and not filas["poco"].elegible


async def test_cierre_idempotente_y_aprobacion(client, db, make_user, make_binary_market):
    ms = [await make_binary_market(f"c{i}") for i in range(5)]
    for m in ms:
        m.status = MarketStatus.RESOLVED_YES
    us = [await make_user(f"u{i}") for i in range(4)]
    for k, u in enumerate(us):
        for i in range(10):
            _trade(db, u, ms[i % 5], 10, 10 + (4 - k))   # u0 > u1 > u2 > u3
    await db.commit()

    cierre = await lb.cerrar_mes(db, OCT)
    assert await lb.cerrar_mes(db, OCT) is None
    assert len((await db.execute(select(LeaderboardMesFila))).scalars().all()) == 4
    assert (await client.get("/api/users/leaderboard/ganadores")).json() == []   # pending no es público

    url = f"/api/admin/leaderboard/meses/{cierre.id}/aprobar"
    assert (await client.get(url, params={"t": "malo"})).status_code == 400
    t = make_plan_token(cierre.id, cierre.nonce, "seed_approval")                  # otro typ no sirve
    assert (await client.get(url, params={"t": t})).status_code == 400
    t = make_plan_token(cierre.id, cierre.nonce, lb.TOKEN_TYP)
    assert (await client.get(url, params={"t": t})).status_code == 200
    r = await client.post(url, params={"t": t}, data={"descalificar": [str(us[1].id)]})
    assert r.status_code == 200, r.text

    [mes] = (await client.get("/api/users/leaderboard/ganadores")).json()
    assert mes["mes"] == "2026-10"
    assert [(g["rank"], g["username"]) for g in mes["ganadores"]] == [(1, "u0"), (2, "u2"), (3, "u3")]
    estado = (await db.execute(select(LeaderboardMes).execution_options(populate_existing=True))).scalar_one()
    assert estado.status == "approved"

    perfil = (await client.get("/api/users/u0")).json()
    assert perfil["trofeos"] == [{"mes": "2026-10", "rank": 1}]
    assert (await client.get("/api/users/u1")).json()["trofeos"] == []   # descalificado


async def test_endpoint_mes_me(client, make_user, make_binary_market, db):
    u = await make_user("yo")
    m = await make_binary_market("x")
    _trade(db, u, m, 10, 20, at=datetime.now(timezone.utc))
    await db.commit()

    r = (await client.get("/api/users/leaderboard/mes", headers=auth_headers(u))).json()
    assert r["min_predicciones"] == lb.MIN_PREDICCIONES and r["yo"]["n_trades"] == 1
    assert r["yo"]["faltan_predicciones"] == lb.MIN_PREDICCIONES - 1 and r["yo"]["faltan_mercados"] == lb.MIN_MERCADOS - 1
    assert r["yo"]["rank"] is None and not r["yo"]["elegible"]
    assert (await client.get("/api/users/leaderboard/mes")).json()["yo"] is None

    [e] = (await client.get("/api/users/leaderboard", params={"period": "month"})).json()
    assert e["username"] == "yo" and e["elegible"] is False and e["volume"] == 10


def test_tipo_aviso():
    cdmx = lambda *a: datetime(*a, tzinfo=lb.MX)  # noqa: E731
    assert lb.tipo_aviso(cdmx(2026, 9, 28, 10)) is None               # septiembre: sin premios
    assert lb.tipo_aviso(cdmx(2026, 10, 5, 8, 59)) is None            # lunes antes de las 9
    assert lb.tipo_aviso(cdmx(2026, 10, 5, 9)) == "semana-41"
    assert lb.tipo_aviso(cdmx(2026, 10, 6, 9)) is None                # martes
    assert lb.tipo_aviso(cdmx(2026, 10, 29, 0)) == "ultimos"          # 72 h antes del 1-nov
    assert lb.tipo_aviso(cdmx(2026, 10, 28, 23)) is None


async def test_avisos_una_vez_y_opt_out(db, make_user, make_binary_market, monkeypatch):
    from app.services import email as email_mod
    enviados = []

    async def fake(to, *a, **kw):
        enviados.append((to, kw))
    monkeypatch.setattr(email_mod, "send_competencia_email", fake)

    m = await make_binary_market("av")
    si, no = await make_user("si"), await make_user("no")
    no.email_notifications = False
    await make_user("nada")                                         # no operó
    lunes = datetime(2026, 10, 5, 16, tzinfo=timezone.utc)          # 10:00 CDMX
    for u in (si, no):
        _trade(db, u, m, 10, 20, at=lunes - timedelta(days=1))
    await db.commit()

    assert await lb.avisos_competencia(lunes) == 1
    assert await lb.avisos_competencia(lunes + timedelta(hours=2)) == 0   # misma semana: no repite
    assert [to for to, _ in enviados] == ["si@test.local"]
    assert enviados[0][1]["rank"] is None and enviados[0][1]["faltan_predicciones"] == lb.MIN_PREDICCIONES - 1
    assert not enviados[0][1]["ultimos"]


async def test_correo_competencia(monkeypatch):
    from app.services import email as email_mod
    out = []

    async def fake_send(to, subject, html, text=None):
        out.append((subject, html, text))
    monkeypatch.setattr(email_mod, "_send", fake_send)
    await email_mod.send_competencia_email("a@b.mx", "Ana", ultimos=True, dias=2, rank=5, ganancia=120.0,
                                           para_podio=80.0, faltan_predicciones=0, faltan_mercados=0)
    subject, html, text = out[0]
    assert subject == "Últimos días: vas en el lugar 5 del mes"
    assert "+120 PT" in html and "80 PT para el podio" in text and "/#/clasificacion" in html


async def test_pnl_historico_solo_trades(client, db, make_user, make_binary_market):
    """Perfil, gráfica y leaderboard «Todo»: solo trades realizados, sin bonos."""
    u = await make_user("pnl")
    u.points += 700                      # bono diario + referido: no es ganancia
    u.markets_traded = 4
    gana, pierde, cancelado, abierto = [await make_binary_market(f"p{i}") for i in range(4)]
    ahora = datetime.now(timezone.utc)
    for m, st in ((gana, MarketStatus.RESOLVED_YES), (pierde, MarketStatus.RESOLVED_NO), (cancelado, MarketStatus.CANCELLED)):
        m.status, m.resolved_at = st, ahora
    _trade(db, u, gana, 40, 100, at=ahora)       # +60
    _trade(db, u, pierde, 25, 100, at=ahora)     # −25
    _trade(db, u, cancelado, 30, 60, at=ahora)   # 0
    _trade(db, u, abierto, 50, 100, at=ahora)    # sin resolver: 0
    await db.commit()

    assert (await client.get(f"/api/users/{u.username}")).json()["pnl"] == 35
    [fila] = (await client.get("/api/users/leaderboard?period=all")).json()
    assert fila["pnl"] == 35
    hist = (await client.get("/api/users/me/points-history", headers=auth_headers(u))).json()
    assert hist[-1]["price"] == 35 and hist[0]["price"] in (0, 35)
