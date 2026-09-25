"""Agente de siembra (app/services/siembra): 1X2 con prior de dos fuentes y
duplicados; escaleras y rangos de Crypto; plan con correo, página de casillas y
aplicación de un solo uso. Sin red: ESPN, Binance, Kraken y DefiLlama simulados."""
import asyncio
import math
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.market import Market
from app.models.seed_plan import SeedPlan
from app.services import email as email_mod
from app.services.resolucion import nocturno
from app.services.resolucion.fuentes import Partido
from app.services.siembra import cripto as C, job, partidos as P
from tests.fakes import FakeHttp
from tests.test_escaleras_crypto import MESES, umbral

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


def test_fecha_fifa_sin_tabla_en_espanol_y_cruza():
    from app.services.resolucion.cruce import emparejar
    ahora = datetime(2026, 9, 24, 14, tzinfo=timezone.utc)
    k = ahora + timedelta(days=2)
    p = Partido(fuente="espn", id="9", url="https://www.espn.com/soccer/match/_/gameId/9", kickoff=k,
                home="United States", away="Mexico", home_score=None, away_score=None, estado="SCHEDULED",
                alias=["United States", "USA", "|", "Mexico", "MEX"], liga="Fecha FIFA", equipo_ids=("660", "203"),
                cuotas=CUOTAS_CRUZ_TOLUCA)
    prop, motivo = P.propuesta(p, "Fecha FIFA", {}, ahora)
    assert motivo is None and prop["titulo"] == "Estados Unidos vs México"
    assert prop["revisar"] and len(prop["doc"]["context"]) >= 120
    # el resolvedor cruza la pregunta en español con los nombres de ESPN
    assert emparejar("Estados Unidos", "México", k, [p])[0] is p
    # el mismo partido ya abierto con etiquetas en español es duplicado
    assert P.es_duplicado(p, "Fecha FIFA", [{"subcategory": "Fecha FIFA", "kickoff_at": k,
                                              "labels": ["🏠 Estados Unidos", "🤝 Empate", "✈️ México"]}])


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
    row = await job.correr_siembra()
    assert row.status == "pending" and row.resumen["propuestas"] == 2
    await asyncio.sleep(0)  # el correo sale con spawn()
    assert correos and "2 mercados" in correos[0][0]
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
    assert await job.correr_siembra() is None


# ── Crypto ──────────────────────────────────────────────────────────────────

def test_mes_objetivo():
    assert C.mes_objetivo(date(2026, 9, 24)) == date(2026, 10, 31)   # quedan 6 días → el siguiente
    assert C.mes_objetivo(date(2026, 10, 5)) == date(2026, 10, 31)
    assert C.mes_objetivo(date(2026, 12, 25)) == date(2027, 1, 31)


def _klines(spot: float) -> list:
    """91 velas diarias con ±2% alternado (σ diaria ≈ 2%) que terminan en `spot`."""
    cl = [spot * math.exp(0.02 * (1 if i % 2 else -1)) for i in range(90)] + [spot]
    return [[0, 0, 0, 0, str(c)] for c in cl]


def _defillama(nivel: float) -> list:
    hoy = datetime(2026, 9, 24, tzinfo=timezone.utc)
    return [{"date": str(int((hoy - timedelta(days=60 - i)).timestamp())),
             "totalCirculatingUSD": {"peggedUSD": nivel * (1 + 0.0005 * (i - 60)) * (1.001 if i % 2 else 0.999)}}
            for i in range(61)]


def _cripto_http(binance: bool = True) -> FakeHttp:
    m = {"stablecoincharts": _defillama(310e9)}
    if binance:
        m.update({"symbol=BTCUSDT": _klines(84_000), "symbol=ETHUSDT": _klines(2_700), "symbol=SOLUSDT": _klines(117)})
    else:
        m.update({f"pair={p}": {"error": [], "result": {f"X{p}": [[0, 0, 0, 0, str(v)] for v in [r[4] for r in _klines(s)]], "last": 1}}
                  for p, s in (("XBTUSD", 84_000), ("ETHUSD", 2_700), ("SOLUSD", 117))})
    return FakeHttp(m)


def test_escaleras_y_rangos_de_cripto():
    ahora = datetime(2026, 9, 24, 14, tzinfo=timezone.utc)
    props, desc = C.armar_propuestas(_cripto_http(), ahora, set())
    assert desc == []
    escaleras: dict[str, list] = {}
    for x in props:
        d = x["doc"]
        assert d["ends_at"].startswith("2026-10-31")
        if d["tipo"] == "binario":
            mes, n = umbral(d["question"])   # la landing la reconoce como escalera
            assert mes == MESES[9] and n == d["auto_resolucion"]["valor"] and d["auto_resolucion"]["op"] == ">="
            assert C.PRIOR_MIN <= d["initial_yes_price"] <= C.PRIOR_MAX and len(d["question"]) <= 70
            escaleras.setdefault(d["subcategory"], []).append(n)
        else:
            pcts = [o["pct"] for o in d["outcomes"]]
            assert sum(pcts) == 100 and min(pcts) >= C.MIN_OPCION
            assert d["outcomes"][0]["key"].startswith("r_menos_") and d["outcomes"][-1]["key"].endswith("_mas")
    assert set(escaleras) == {"Bitcoin", "Ethereum", "Solana", "Stablecoins"}
    for sub, ns in escaleras.items():
        assert len(ns) >= C.MIN_PELDANOS and ns == sorted(ns), sub
    assert sum(1 for x in props if x["doc"]["tipo"] == "multi") == 3

    # ya sembrado (escalera y rango de BTC) → no se repite; sin Binance cae a Kraken
    excluir = {"btc-cierre-oct26-85000", "btc-rango-cierre-oct26"}
    props2, desc2 = C.armar_propuestas(_cripto_http(binance=False), ahora, excluir)
    assert desc2 == [] and not any(x["grupo"] == "Bitcoin" for x in props2)
    assert "Kraken" in next(x["nota"] for x in props2 if x["grupo"] == "Ethereum")


def test_rangos_juntan_puntas_chicas():
    prior = lambda K: C._N(math.log(100 / K) / 0.05)   # distribución angosta alrededor de 100
    cortes, pcts = C.rangos([60, 80, 100, 120, 140], prior)
    assert sum(pcts) == 100 and min(pcts) >= C.MIN_OPCION and len(cortes) >= 1


# ── Economía ────────────────────────────────────────────────────────────────

from app.services.siembra import economia as E  # noqa: E402

FED_HTML = ('<h4>2026 FOMC Meetings</h4><div class="fomc-meeting__month"><strong>October</strong></div>'
            '<div class="fomc-meeting__date">27-28</div><div class="fomc-meeting__month"><strong>December</strong></div>'
            '<div class="fomc-meeting__date">8-9*</div><h4>2027 FOMC Meetings</h4>'
            '<div class="fomc-meeting__month"><strong>Jan/Feb</strong></div><div class="fomc-meeting__date">31-1</div>')


def _poly(titulo: str, end: str, precios: dict) -> dict:
    return {"title": titulo, "endDate": end, "closed": False, "slug": "x", "volume": "1000",
            "markets": [{"groupItemTitle": k, "outcomePrices": f'["{v}", "{1 - v}"]'} for k, v in precios.items()]}


def _eco_http(kalshi_mantiene: str = "0.34") -> FakeHttp:
    return FakeHttp(
        json_map={
            "Fed%20decision": {"events": [_poly("Fed Decision in October?", "2026-10-29T03:59:00Z",
                                                {"25 bps decrease": 0.01, "No change": 0.35, "25 bps increase": 0.64})]},
            "Bank%20of%20Mexico": {"events": [
                _poly("Bank of Mexico Decision in November?", "2026-11-05T23:59:00Z",
                      {"25 bps decrease": 0.03, "No change": 0.70, "25 bps increase": 0.20}),
                {**_poly("Bank of Mexico Decision in March?", "2026-03-26T00:00:00Z", {"No change": 1.0}), "closed": True}]},
            "kalshi": {"markets": [{"ticker": "KXFEDDECISION-26OCT-C25", "yes_bid_dollars": "0.01", "yes_ask_dollars": "0.01"},
                                   {"ticker": "KXFEDDECISION-26OCT-H0", "yes_bid_dollars": kalshi_mantiene, "yes_ask_dollars": kalshi_mantiene},
                                   {"ticker": "KXFEDDECISION-26OCT-H25", "yes_bid_dollars": "0.65", "yes_ask_dollars": "0.65"}]},
            "SF61745": {"bmx": {"series": [{"datos": [{"fecha": "24/09/2026", "dato": "6.50"}]}]}},
            "SP30578": {"bmx": {"series": [{"datos": [{"fecha": "01/08/2026", "dato": "3.26"}]}]}},
        },
        text_map={"fomccalendars": FED_HTML, "DFEDTARU": "observation_date,DFEDTARU\n2026-09-23,4.00\n"},
    )


def test_fomc_fechas_y_pct_min():
    assert E.fomc_fechas(_eco_http()) == [date(2026, 10, 28), date(2026, 12, 9), date(2027, 2, 1)]
    out = E.pct_min([0.008, 0.355, 0.646])
    assert sum(out) == 100 and min(out) >= E.MIN_OPCION


def test_economia_propone_fed_banxico_e_inflacion(monkeypatch):
    monkeypatch.setattr(E.settings, "BANXICO_TOKEN", "t")
    ahora = datetime(2026, 9, 24, 14, tzinfo=timezone.utc)
    props, desc = E.armar_propuestas(_eco_http(), ahora, set())
    assert desc == []
    por_id = {x["doc"]["id"]: x for x in props}
    assert set(por_id) == {"fed-decision-oct26", "banxico-decision-nov26", "inflacion-sep26-menor-325"}
    fed, bx, inf = por_id["fed-decision-oct26"], por_id["banxico-decision-nov26"], por_id["inflacion-sep26-menor-325"]
    assert fed["doc"]["ends_at"] == "2026-10-28T17:55:00Z" and fed["revisar"] == []
    assert [o["key"] for o in fed["doc"]["outcomes"]] == ["baja", "mantiene", "sube"]
    assert min(o["pct"] for o in fed["doc"]["outcomes"]) >= E.MIN_OPCION
    assert bx["revisar"] == ["una sola fuente (Polymarket)"] and "6.50%" in bx["doc"]["context"]
    assert inf["doc"]["auto_resolucion"] == {"fuente": "inflacion_anual", "params": {"periodo": "2026-09"}, "op": "<", "valor": 3.25}
    assert inf["doc"]["ends_at"] == "2026-10-07T05:59:00Z" and inf["doc"]["initial_yes_price"] == 50

    # lo ya sembrado no se repite (el binario «sin cambio» de noviembre cuenta); la inflación pasa al mes siguiente
    props, _ = E.armar_propuestas(_eco_http(), ahora, {"banxico-sin-cambio-nov26", "fed-decision-oct26", "inflacion-sep26-menor-340"})
    assert [x["doc"]["id"] for x in props] == ["inflacion-oct26-menor-325"]

    # Kalshi muy distinto → revisar
    props, _ = E.armar_propuestas(_eco_http(kalshi_mantiene="0.60"), ahora, set())
    assert "difieren" in next(x for x in props if x["doc"]["id"] == "fed-decision-oct26")["revisar"][0]

    # sin token de Banxico: la inflación sale en descartes, la Fed sigue
    monkeypatch.setattr(E.settings, "BANXICO_TOKEN", "")
    props, desc = E.armar_propuestas(_eco_http(), ahora, set())
    assert "fed-decision-oct26" in {x["doc"]["id"] for x in props} and any("BANXICO_TOKEN" in d["motivo"] for d in desc)


# ── Revisor de reglas y propuestas de la rutina creativa ────────────────────

from app.services.siembra import filtros as F  # noqa: E402
from tests.conftest import auth_headers  # noqa: E402

_EV = {"tendencia_url": "https://trends.google.com/x", "fuente_prior": "Polymarket 42%", "score_total": 9}


def _creativa(**cambios) -> dict:
    ahora = datetime.now(timezone.utc)
    doc = {
        "tipo": "binario", "id": "sheinbaum-trump-x-oct26",
        "question": "¿Sheinbaum le contestará a Trump en X antes del 15 de octubre?",
        "description": "Resuelve SÍ si la cuenta oficial de Claudia Sheinbaum en X publica una respuesta directa a Trump.",
        "category": "POLITICA_MX", "subcategory": "Sheinbaum",
        "resolution_criteria": "Publicación en la cuenta oficial @Claudiashein que mencione o responda a Donald Trump.",
        "resolution_source_url": "https://x.com/Claudiashein",
        "rules_cuerpo": "Cuenta cualquier publicación, respuesta o cita en la cuenta oficial de Claudia Sheinbaum en X que "
                        "mencione a Donald Trump por nombre o responda a una publicación suya, hecha antes del cierre.",
        "context": "Sheinbaum y Trump han intercambiado mensajes públicos sobre aranceles y migración durante 2026; la "
                   "presidenta suele responder en la mañanera más que en redes sociales.",
        "ends_at": (ahora + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ"), "initial_yes_price": 42,
    }
    base = {"doc": doc, "evidencia": dict(_EV), "loco": False}
    for k, v in cambios.items():
        (base if k in ("evidencia", "loco") else doc)[k] = v
    return base


def test_filtros_reglas():
    ahora = datetime.now(timezone.utc)
    r = lambda p, **kw: F.revisar(p, ahora, kw.get("vigentes", set()), kw.get("abiertas", []), kw.get("locos", 0))
    assert r(_creativa()) is None
    assert "lista negra" in r(_creativa(question="¿Habrá un atentado en el Zócalo antes del 15 de octubre?"))
    assert "70" in r(_creativa(question="¿" + "x" * 80 + "?"))
    assert "subcategoría" in r(_creativa(subcategory="Chismes"))
    assert "10–90" in r(_creativa(initial_yes_price=5))
    assert r(_creativa(initial_yes_price=5, loco=True)) is None
    assert "1–15" in r(_creativa(initial_yes_price=40, loco=True))
    assert "plazo" in r(_creativa(ends_at=(ahora + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")))
    assert "evidencia" in r(_creativa(evidencia={"score_total": 9}))
    assert "score" in r(_creativa(evidencia={**_EV, "score_total": 6}))
    assert "ya existe" in r(_creativa(), vigentes={"sheinbaum-trump-x-oct26"})
    assert "duplicado" in r(_creativa(), abiertas=["¿Sheinbaum contestará a Trump en X antes del 15 de octubre?"])
    assert "locos" in r(_creativa(initial_yes_price=5, loco=True), locos=5)
    assert r(_creativa(question="¿Habrá desfile de Día de Muertos en la CDMX este año?")) is None


def test_lote_no_repite_dentro_del_mismo_envio():
    ahora = datetime.now(timezone.utc)
    ok, desc = F.revisar_lote([_creativa(), _creativa(id="otro-id")], ahora, set(), [], 0)
    assert len(ok) == 1 and "duplicado" in desc[0]["motivo"]
    assert ok[0]["nota"].startswith("score 9/12")


async def test_proponer_por_clave_y_dry_run(client, db, correos, make_user, monkeypatch):
    from app.api import siembra as api
    monkeypatch.setattr(api.settings, "SIEMBRA_API_KEY", "clave-secreta")
    body = {"propuestas": [_creativa(), _creativa(id="malo", subcategory="Chismes")], "nota": "rutina lunes"}

    r = await client.post("/api/admin/siembra/planes/proponer", json=body)
    assert r.status_code == 403
    r = await client.post("/api/admin/siembra/planes/proponer", json=body, headers={"X-Siembra-Key": "otra"})
    assert r.status_code == 403
    u = await make_user("normal")
    r = await client.post("/api/admin/siembra/planes/proponer", json=body, headers=auth_headers(u))
    assert r.status_code == 403

    r = await client.post("/api/admin/siembra/planes/proponer?dry_run=true", json=body, headers={"X-Siembra-Key": "clave-secreta"})
    assert r.status_code == 200 and r.json()["plan_id"] is None and r.json()["aceptadas"] == ["sheinbaum-trump-x-oct26"]
    assert (await db.execute(select(SeedPlan))).first() is None

    r = await client.post("/api/admin/siembra/planes/proponer", json=body, headers={"X-Siembra-Key": "clave-secreta"})
    pid = r.json()["plan_id"]
    assert pid and "subcategoría" in r.json()["descartes"][0]["motivo"]
    await asyncio.sleep(0)
    assert correos and "1 mercados" in correos[-1][0]
    plan = (await db.execute(select(SeedPlan).where(SeedPlan.id == pid))).scalar_one()
    t = nocturno.make_plan_token(pid, plan.nonce, job.TOKEN_TYP)
    r = await client.post(f"/api/admin/siembra/planes/{pid}/aprobar?t={t}", data={"ids": ["sheinbaum-trump-x-oct26"]})
    assert "Sembrados (1)" in r.text
    # ya propuesto → la siguiente vez sale como existente
    r = await client.post("/api/admin/siembra/planes/proponer?dry_run=true", json=body, headers={"X-Siembra-Key": "clave-secreta"})
    assert r.json()["aceptadas"] == []
