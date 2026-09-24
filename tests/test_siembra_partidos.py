"""Agente de siembra de 1X2 (app/services/siembra): prior de dos fuentes,
duplicados, plan con correo, página de casillas y aplicación de un solo uso.
Sin red: ESPN simulado con FakeHttp."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.market import Market
from app.models.seed_plan import SeedPlan
from app.services import email as email_mod
from app.services.resolucion import nocturno
from app.services.resolucion.fuentes import Partido
from app.services.siembra import job, partidos as P
from tests.fakes import FakeHttp

CUOTAS_CRUZ_TOLUCA = {"local": "+165", "empate": "+230", "visitante": "+155"}  # ESPN, 24-sep-2026


def test_prob_cuotas_quita_el_margen():
    l, e, v = P.prob_cuotas(CUOTAS_CRUZ_TOLUCA)
    assert abs(l + e + v - 1) < 1e-9
    assert v > l > e  # Toluca de visita, favorito leve
    assert P.prob_cuotas({"local": "+100"}) is None
    assert P.prob_americana("-200") == pytest.approx(2 / 3)


def test_prob_tabla_y_pocos_partidos():
    fuerte, debil = {"pj": 9, "pts": 24}, {"pj": 9, "pts": 5}
    l, e, v = P.prob_tabla(fuerte, debil)
    assert l > 0.6 and v < 0.15 and abs(l + e + v - 1) < 1e-9
    assert P.prob_tabla({"pj": 2, "pts": 6}, debil) is None


def test_ints_100():
    for ps in [(0.995, 0.004, 0.001), (1 / 3, 1 / 3, 1 / 3), (0.35, 0.28, 0.37)]:
        out = P.ints_100(ps)
        assert sum(out) == 100 and min(out) >= 1


def _partido(kickoff: datetime, cuotas=CUOTAS_CRUZ_TOLUCA) -> Partido:
    return Partido(fuente="espn", id="1", url="https://www.espn.com/soccer/match/_/gameId/1", kickoff=kickoff,
                   home="Cruz Azul", away="Toluca", home_score=None, away_score=None, estado="SCHEDULED",
                   alias=["Cruz Azul", "CAZ", "|", "Toluca", "TOL"], liga="Liga MX", equipo_ids=("218", "223"),
                   cuotas=cuotas)


def _tabla(pts_local=17, pj=9) -> dict:
    return {"218": {"nombre": "Cruz Azul", "pj": pj, "pts": pts_local, "rank": 3, "grupos": 1},
            "223": {"nombre": "Toluca", "pj": 9, "pts": 19, "rank": 1, "grupos": 1}}


def test_propuesta_valida_y_revisar():
    ahora = datetime(2026, 9, 24, 14, tzinfo=timezone.utc)
    prop, motivo = P.propuesta(_partido(ahora + timedelta(days=2)), "Liga MX", _tabla(), ahora)
    assert motivo is None and prop["revisar"] == []
    assert prop["doc"]["id"] == "liga-mx-cruz-azul-toluca-20260926"
    assert sum(prop["doc"]["pct"]) == 100 and len(prop["doc"]["context"]) >= 120

    # la tabla dice otra cosa (Cruz Azul con 27 de 27) → revisar
    prop, _ = P.propuesta(_partido(ahora + timedelta(days=2)), "Liga MX", _tabla(pts_local=27), ahora)
    assert prop["revisar"] and "difieren" in prop["revisar"][0]
    # tabla con pocos partidos → revisar, abre con cuotas
    prop, _ = P.propuesta(_partido(ahora + timedelta(days=2)), "Liga MX", _tabla(pj=2, pts_local=6), ahora)
    assert "menos de 3" in prop["revisar"][0]
    # sin cuotas o sin tabla → descartado
    assert P.propuesta(_partido(ahora + timedelta(days=2), cuotas=None), "Liga MX", _tabla(), ahora)[1]
    assert P.propuesta(_partido(ahora + timedelta(days=2)), "Liga MX", {}, ahora)[1]


def test_duplicado_con_otro_id():
    k = datetime(2026, 9, 27, 2, tzinfo=timezone.utc)
    mismo = [{"subcategory": "Liga MX", "kickoff_at": k + timedelta(hours=1), "labels": ["🏠 Cruz Azul", "🤝 Empate", "✈️ Toluca"]}]
    assert P.es_duplicado(_partido(k), "Liga MX", mismo)
    assert not P.es_duplicado(_partido(k), "Liga MX", [{**mismo[0], "subcategory": "MLS"}])
    assert not P.es_duplicado(_partido(k), "Liga MX", [{**mismo[0], "kickoff_at": k + timedelta(days=3)}])


# ── flujo completo ──────────────────────────────────────────────────────────

@pytest.fixture
def correos(monkeypatch):
    enviados: list[tuple[str, str]] = []

    async def fake_send(to, subject, html, **kw):
        enviados.append((subject, html))

    monkeypatch.setattr(email_mod, "_send", fake_send)
    return enviados


def _evento(eid: str, kickoff: datetime, home: tuple[str, str], away: tuple[str, str]) -> dict:
    ml = {k: {"close": {"odds": v}} for k, v in zip(("home", "draw", "away"), ("+165", "+230", "+155"))}
    return {"id": eid, "date": kickoff.strftime("%Y-%m-%dT%H:%MZ"),
            "status": {"type": {"name": "STATUS_SCHEDULED", "completed": False}},
            "competitions": [{"odds": [{"moneyline": ml}], "competitors": [
                {"homeAway": "home", "team": {"id": home[0], "displayName": home[1]}},
                {"homeAway": "away", "team": {"id": away[0], "displayName": away[1]}}]}]}


@pytest.fixture
def espn(monkeypatch):
    k = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=2)
    entradas = [{"team": {"id": i, "displayName": n}, "stats": [{"name": "gamesPlayed", "value": 9},
                 {"name": "points", "value": pts}, {"name": "rank", "value": r}]}
                for i, n, pts, r in [("218", "Cruz Azul", 17, 3), ("223", "Toluca", 19, 1),
                                     ("226", "Atlante", 8, 14), ("220", "Monterrey", 13, 10)]]
    fake = FakeHttp({
        "mex.1/scoreboard": {"events": [_evento("1", k, ("218", "Cruz Azul"), ("223", "Toluca")),
                                        _evento("2", k + timedelta(hours=2), ("226", "Atlante"), ("220", "Monterrey"))]},
        "/scoreboard": {"events": []},
        "mex.1/standings": {"children": [{"standings": {"entries": entradas}}]},
    })
    monkeypatch.setattr(job, "Http", lambda: fake)
    return fake


async def test_plan_casillas_y_un_solo_uso(client, db, correos, espn):
    row = await job.correr_siembra_partidos()
    assert row.status == "pending" and row.resumen["propuestas"] == 2
    await asyncio.sleep(0)  # el correo sale con spawn()
    assert correos and "2 partidos" in correos[0][0]
    ids = [x["doc"]["id"] for x in row.plan["propuestas"]]

    t = nocturno.make_plan_token(row.id, row.nonce, job.TOKEN_TYP)
    r = await client.get(f"/api/admin/siembra/planes/{row.id}/aprobar?t={t}")
    assert r.status_code == 200 and r.text.count("type='checkbox'") == 2
    assert (await db.execute(select(Market))).first() is None  # el GET no siembra

    # un token de resolución no aprueba una siembra
    otro = nocturno.make_plan_token(row.id, row.nonce)
    r = await client.post(f"/api/admin/siembra/planes/{row.id}/aprobar?t={otro}", data={"ids": ids[:1]})
    assert r.status_code == 400
    assert nocturno.verify_plan_token(t, row.id) is None

    r = await client.post(f"/api/admin/siembra/planes/{row.id}/aprobar?t={t}", data={"ids": ids[:1]})
    assert r.status_code == 200 and "Sembrados (1)" in r.text and "Desmarcados (1)" in r.text
    m = (await db.execute(select(Market))).scalars().all()
    assert [x.id for x in m] == ids[:1] and m[0].kind == "partido" and m[0].kickoff_at is not None
    plan = (await db.execute(select(SeedPlan).execution_options(populate_existing=True))).scalar_one()
    assert plan.status == "applied" and plan.resultado["desmarcados"] == ids[1:]

    # segundo clic: no hace nada; siguiente corrida: nada nuevo (sembrado y desmarcado)
    r = await client.post(f"/api/admin/siembra/planes/{row.id}/aprobar?t={t}", data={"ids": ids})
    assert "ya no está pendiente" in r.text
    assert len((await db.execute(select(Market))).scalars().all()) == 1
    assert await job.correr_siembra_partidos() is None
