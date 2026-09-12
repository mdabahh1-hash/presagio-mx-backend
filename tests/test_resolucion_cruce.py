"""Cruce mercado ↔ partido y veredicto mecánico (resolucion/cruce.py). Sin red."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.resolucion import cruce
from app.services.resolucion.fuentes import AET, FT, POSTPONED, SCHEDULED, Partido

K = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)


def P(home, away, hs=None, as_=None, estado=FT, fuente="espn", dt=K, alias=None, id="1"):
    return Partido(fuente=fuente, id=id, url=f"https://{fuente}.test/{id}", kickoff=dt, home=home, away=away,
                   home_score=hs, away_score=as_, estado=estado, alias=alias or [])


# ── nombres ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("Inter", "Internazionale"), ("Inter", "Inter Milan"), ("Colonia", "1. FC Köln"),
    ("Bayern Múnich", "Bayern Munich"), ("Athletic Club", "Athletic Bilbao"),
    ("Atlético de Madrid", "Atlético Madrid"), ("Nacional", "Nacional de Madeira"),
    ("Guadalajara", "CD Guadalajara"), ("Al-Fayha", "Al Fayha"), ("D.C. United", "DC United"),
    ("Estrela Amadora", "Estrela"), ("LASK", "LASK Linz"), ("Sporting CP", "Sporting Lisbon"),
    ("Racing Santander", "Racing de Santander"), ("Deportivo", "Deportivo La Coruña"),
    ("AC Milan", "Milan"), ("Borussia Mönchengladbach", "Borussia Monchengladbach"),
    ("D.C. United", "DC United"), ("SC Paderborn 07", "Paderborn"), ("TSG Hoffenheim", "Hoffenheim"),
])
def test_mismo_club(a, b):
    assert cruce.similitud(a, b) >= cruce.UMBRAL, (a, b, cruce.similitud(a, b))


@pytest.mark.parametrize("a,b", [
    ("Real Madrid", "Atlético Madrid"), ("Real Sociedad", "Real Madrid"), ("Al Hilal", "Al Nassr"),
    ("Manchester City", "Manchester United"), ("Genoa", "Como"), ("Sevilla", "Real Betis"),
])
def test_club_distinto(a, b):
    assert cruce.similitud(a, b) < cruce.UMBRAL, (a, b, cruce.similitud(a, b))


def test_variantes_nombre():
    from app.services.resolucion.fuentes import variantes_nombre
    v = variantes_nombre("FC Porto", "Porto")
    assert v[0] == "FC Porto" and "Porto" in v
    v = variantes_nombre("Inter Miami CF")
    assert "Inter Miami" in v
    v = variantes_nombre("Al Fayha")
    assert "Al-Fayha" in v
    v = variantes_nombre("Brighton & Hove Albion")
    assert v[0] == "Brighton and Hove Albion"
    assert "Hoffenheim" in variantes_nombre("TSG Hoffenheim")
    assert "Paderborn" in variantes_nombre("SC Paderborn 07")
    assert "DC United" in variantes_nombre("D.C. United")
    v = variantes_nombre("Red Bull New York", "New York Red Bulls")
    assert v[0] == "New York Red Bulls" and v.count("New York Red Bulls") == 1


# ── parseo ───────────────────────────────────────────────────────────────────

def test_equipos_por_labels():
    m = {"question": "¿Quién ganará Inter vs. Napoli?",
         "outcomes": [{"outcome_key": "local", "label": "🏠 Inter"}, {"outcome_key": "empate", "label": "🤝 Empate"},
                      {"outcome_key": "visitante", "label": "✈️ Napoli"}]}
    assert cruce.equipos_partido(m) == ("Inter", "Napoli")


def test_equipos_por_pregunta():
    assert cruce.equipos_partido({"question": "¿Quién gana Atlante vs León?"}) == ("Atlante", "León")
    assert cruce.equipos_partido({"question": "Colonia vs. Hoffenheim — ¿quién gana? (Bundesliga Jornada 1)"}) == ("Colonia", "Hoffenheim")
    assert cruce.equipos_partido({"question": "¿Cody Gakpo será titular en Liverpool vs Nottingham Forest?"}) is None


def test_parse_titular():
    assert cruce.parse_titular({"question": "¿Mateo Kovačić será titular en Crystal Palace vs Manchester City?"}) == \
        {"jugador": "Mateo Kovačić", "equipos": ["Crystal Palace", "Manchester City"]}
    assert cruce.parse_titular({"question": "¿Rayan Cherki será titular con Manchester City ante Porto en la Jornada 1 de la Champions?"}) == \
        {"jugador": "Rayan Cherki", "equipos": ["Manchester City", "Porto"]}


def test_parse_gol():
    r = cruce.parse_gol({"question": "¿Erling Haaland anota gol ante Porto en la Jornada 1 de la Champions?"})
    assert r["jugador"] == "Erling Haaland" and r["equipos"] == ["Porto"]
    r = cruce.parse_gol({"question": "¿Kylian Mbappé marcará al menos un gol en su primer partido de la Champions 2026/27?"})
    assert r == {"jugador": "Kylian Mbappé", "equipos": []}
    assert cruce.parse_gol({"question": "¿Quién ganará Inter vs. Napoli?"}) is None
    assert cruce.parse_gol({"question": "¿Cody Gakpo será titular en Liverpool vs Nottingham Forest?"}) is None


# ── emparejar ────────────────────────────────────────────────────────────────

JORNADA = [
    P("Internazionale", "Napoli", 3, 2, alias=["Internazionale", "Inter Milan", "|", "Napoli"], id="a"),
    P("AS Roma", "Atalanta", 2, 1, dt=K + timedelta(hours=2, minutes=45), id="b"),
    P("Fiorentina", "Torino", 1, 2, dt=K - timedelta(hours=3), id="c"),
    P("Real Madrid", "Málaga", 4, 0, dt=K + timedelta(days=3), id="d"),
]


def test_emparejar_directo():
    p, nota = cruce.emparejar("Inter", "Napoli", K, JORNADA)
    assert p is not None and p.id == "a" and nota == ""


def test_emparejar_fuera_de_ventana():
    p, nota = cruce.emparejar("Real Madrid", "Málaga", K, JORNADA)
    assert p is None and "sin cruce" in nota
    p, nota = cruce.emparejar("Real Madrid", "Málaga", K + timedelta(days=10), JORNADA)
    assert p is None and "ningún partido" in nota


def test_emparejar_sede_invertida():
    p, nota = cruce.emparejar("Napoli", "Inter", K, JORNADA)
    assert p is None and "sede invertida" in nota


def test_emparejar_sin_cruce():
    p, nota = cruce.emparejar("Juventus", "Milan", K, JORNADA)
    assert p is None and "sin cruce" in nota


# ── veredicto ────────────────────────────────────────────────────────────────

def test_veredictos():
    assert cruce.veredicto_1x2(P("A", "B", 2, 1)) == ("local", "")
    assert cruce.veredicto_1x2(P("A", "B", 1, 1)) == ("empate", "")
    assert cruce.veredicto_1x2(P("A", "B", 0, 3)) == ("visitante", "")
    assert cruce.veredicto_1x2(P("A", "B", estado=POSTPONED))[0] is None
    assert cruce.veredicto_1x2(P("A", "B", estado=SCHEDULED))[0] is None
    assert cruce.veredicto_1x2(P("A", "B", 2, 2, estado=AET))[0] is None


MERCADO = {"id": "sa-inter-napoli-j3-2627", "volume": 0, "num_trades": 0}


def test_resolver_doble_fuente_coincide():
    e = cruce.resolver_1x2(MERCADO, P("Internazionale", "Napoli", 3, 2), "", P("Inter Milan", "Napoli", 3, 2, fuente="tsdb", id="t"))
    assert e["veredicto"] == "local" and e["confianza"] == "alta"
    assert e["fuente_1"].startswith("https://espn") and e["fuente_2"].startswith("https://tsdb")
    assert "3-2" in e["resultado"]


def test_resolver_fuentes_discrepan():
    e = cruce.resolver_1x2(MERCADO, P("Inter", "Napoli", 3, 2), "", P("Inter", "Napoli", 2, 2, fuente="tsdb"))
    assert e["escalar"] and "discrepan" in e["razon"]


def test_resolver_una_fuente():
    e = cruce.resolver_1x2(MERCADO, P("Inter", "Napoli", 3, 2), "", None)
    assert e["escalar"] and e["veredicto_sugerido"] == "local"


def test_resolver_aplazado():
    e = cruce.resolver_1x2(MERCADO, P("Inter", "Napoli", estado=POSTPONED), "", None)
    assert e["escalar"] and "aplazado" in e["razon"]


def test_resolver_sin_espn():
    e = cruce.resolver_1x2(MERCADO, None, "sin cruce claro", None)
    assert e["escalar"] and "sin cruce" in e["razon"]


# ── accesorios ───────────────────────────────────────────────────────────────

SUMMARY = {"equipos": {"Manchester City": {"titulares": ["Rayan Cherki", "Erling Haaland"], "banca": ["Phil Foden"]},
                       "Porto": {"titulares": ["Diogo Costa"], "banca": []}},
           "goles": [{"minuto": "12'", "tipo": "Goal", "equipo": "Manchester City", "jugador": "Erling Haaland"},
                     {"minuto": "70'", "tipo": "Own Goal", "equipo": "Manchester City", "jugador": "Diogo Costa"}]}


@pytest.mark.parametrize("a,b,esperado", [
    ("Federico Dimarco", "Federico Valverde", False), ("Álvaro Fidalgo", "Álvaro Valles", False),
    ("Julián Álvarez", "Julian Alvarez", True), ("Cherki", "Rayan Cherki", True),
    ("Mateo Kovačić", "Mateo Kovacic", True), ("Rodri", "Rodri", True), ("Rodri", "Rodrigo Hernández", False),
    ("Fabián Ruiz", "Fabian Ruiz Peña", True), ("Kylian Mbappé", "Kylian Mbappe", True),
    ("Kylian Mbappé", "Ethan Mbappé", False), ("Víctor Guzmán", "Victor Guzman", True),
])
def test_persona_coincide(a, b, esperado):
    assert cruce._persona_coincide(a, b) is esperado


def test_sugerir_titular():
    assert cruce.sugerir_titular("Rayan Cherki", SUMMARY)[0] == "YES"
    assert cruce.sugerir_titular("Phil Foden", SUMMARY)[0] == "NO"
    assert cruce.sugerir_titular("Kevin De Bruyne", SUMMARY)[0] == "NO"
    assert cruce.sugerir_titular("Cherki", {"equipos": {}})[0] is None


def test_sugerir_gol():
    assert cruce.sugerir_gol("Erling Haaland", SUMMARY)[0] == "YES"
    assert cruce.sugerir_gol("Diogo Costa", SUMMARY)[0] == "NO"  # autogol no cuenta
    assert cruce.sugerir_gol("Phil Foden", SUMMARY)[0] == "NO"


# ── NFL ──────────────────────────────────────────────────────────────────────

NFL_OUTS = [("seahawks", "Seahawks"), ("patriots", "Patriots")]


def test_equipos_ganador():
    m = {"outcomes": [{"outcome_key": "seahawks", "label": "🦅 Seahawks"}, {"outcome_key": "patriots", "label": "🇺🇸 Patriots"}]}
    assert cruce.equipos_ganador(m) == NFL_OUTS
    assert cruce.equipos_ganador({"outcomes": [{"outcome_key": "local", "label": "🏠 A"}, {"outcome_key": "visitante", "label": "✈️ B"}]}) is None


def test_resolver_ganador_doble_fuente_y_sede_invertida():
    espn = P("Seattle Seahawks", "New England Patriots", 13, 10, alias=["Seattle Seahawks", "Seahawks", "|", "New England Patriots", "Patriots"])
    tsdb = P("Seattle Seahawks", "New England Patriots", 13, 10, fuente="tsdb")
    p, nota = cruce.emparejar_cualquier_sede(["Patriots", "Seahawks"], K, [espn])
    assert p is espn and nota == ""
    e = cruce.resolver_ganador({"id": "x"}, NFL_OUTS, espn, "", tsdb)
    assert e["veredicto"] == "seahawks" and e["confianza"] == "alta" and "gana Seattle Seahawks" in e["resultado"]
    # misma información con local/visitante al revés en TSDB: no es discrepancia
    tsdb2 = P("New England Patriots", "Seattle Seahawks", 10, 13, fuente="tsdb")
    assert cruce.resolver_ganador({"id": "x"}, NFL_OUTS, espn, "", tsdb2)["veredicto"] == "seahawks"
    # marcador distinto sí lo es
    tsdb3 = P("Seattle Seahawks", "New England Patriots", 13, 17, fuente="tsdb")
    e = cruce.resolver_ganador({"id": "x"}, NFL_OUTS, espn, "", tsdb3)
    assert e["escalar"] and "discrepan" in e["razon"]


def test_resolver_ganador_empate_sugiere_cancelar():
    espn = P("Seattle Seahawks", "New England Patriots", 20, 20)
    tsdb = P("Seattle Seahawks", "New England Patriots", 20, 20, fuente="tsdb")
    e = cruce.resolver_ganador({"id": "x"}, NFL_OUTS, espn, "", tsdb)
    assert e["escalar"] and e["veredicto_sugerido"] == "CANCELAR" and "empate" in e["razon"]
    e = cruce.resolver_ganador({"id": "x"}, NFL_OUTS, espn, "", None)
    assert e["escalar"] and "solo una fuente" in e["razon"]


def test_parse_prop_nfl():
    assert cruce.parse_prop_nfl({"question": "¿Jaxon Smith-Njigba anotará al menos 1 touchdown en la Semana 1?"}) == \
        {"jugador": "Jaxon Smith-Njigba", "tipo": "td", "umbral": 1.0}
    assert cruce.parse_prop_nfl({"question": "¿Drake Maye lanzará 2 o más pases de touchdown en la Semana 1?"}) == \
        {"jugador": "Drake Maye", "tipo": "pases_td", "umbral": 2.0}
    assert cruce.parse_prop_nfl({"question": "¿Christian McCaffrey conseguirá 15 o más puntos de Fantasy NFL (scoring estándar) en la Semana 1?"}) == \
        {"jugador": "Christian McCaffrey", "tipo": "fantasy", "umbral": 15.0}
    assert cruce.parse_prop_nfl({"question": "¿Quién gana 49ers vs Rams?"}) is None


def test_fantasy_y_sugerencias_nfl():
    stafford = {"passing": {"passingYards": "155", "passingTouchdowns": "0", "interceptions": "1"},
                "rushing": {"rushingYards": "-1", "rushingTouchdowns": "0"}}
    pts, _ = cruce.fantasy_estandar(stafford)
    assert pts == 4.1
    jsn = {"receiving": {"receivingYards": "122", "receivingTouchdowns": "1", "receptions": "8"}}
    assert cruce.fantasy_estandar(jsn)[0] == 18.2
    assert cruce.sugerir_prop_nfl({"tipo": "td", "umbral": 1}, jsn)[0] == "YES"
    assert cruce.sugerir_prop_nfl({"tipo": "pases_td", "umbral": 2}, {"passing": {"passingTouchdowns": "1"}})[0] == "NO"
    assert cruce.sugerir_prop_nfl({"tipo": "fantasy", "umbral": 15}, jsn)[0] == "YES"
    assert cruce.sugerir_prop_nfl({"tipo": "fantasy", "umbral": 15}, stafford)[0] == "NO"
    # fumble perdido resta 2
    assert cruce.fantasy_estandar({**jsn, "fumbles": {"fumblesLost": "1"}})[0] == 16.2


# ── accesorios con doble fuente (ESPN + TheSportsDB) ─────────────────────────

def _resumen(titulares, banca, goles=(), cambios=None, url="https://www.espn.com/soccer/lineups/_/gameId/1", completo=True):
    return {"equipos": {"PSG": {"titulares": list(titulares), "banca": list(banca)}},
            "goles": [{"minuto": "17'", "tipo": "Goal", "equipo": "PSG", "jugador": g, "texto": g} for g in goles],
            "cambios": cambios, "url": url, "completo": completo}


def test_participo():
    assert cruce.participo("Dembélé", _resumen(["Ousmane Dembélé"], [])) is True
    assert cruce.participo("Kvaratskhelia", _resumen(["X"], ["Khvicha Kvaratskhelia"], cambios=[])) is False
    assert cruce.participo("Kvaratskhelia", _resumen(["X"], ["Khvicha Kvaratskhelia"], cambios=["Khvicha Kvaratskhelia"])) is True
    assert cruce.participo("Kvaratskhelia", _resumen(["X"], ["Khvicha Kvaratskhelia"], cambios=None)) is None  # TSDB no trae cambios
    assert cruce.participo("Osimhen", _resumen(["X"], ["Y"], cambios=[])) is False  # no convocado
    assert cruce.participo("Osimhen", {"equipos": {}, "cambios": None}) is None


def test_resolver_accesorio_titular_y_gol():
    partido = P("PSG", "Slovan", 6, 1)
    m = {"id": "x"}
    espn = _resumen(["Fabián Ruiz", "Ousmane Dembélé"], ["Khvicha Kvaratskhelia"], goles=["Ousmane Dembélé"], cambios=[])
    tsdb = _resumen(["Fabian Ruiz", "Ousmane Dembele"], ["Khvicha Kvaratskhelia"], goles=["Ousmane Dembele"], url="https://www.uefa.com/uefachampionsleague/match/1/")
    e = cruce.resolver_accesorio(m, {"jugador": "Fabián Ruiz"}, "titular", partido, espn, tsdb)
    assert e["veredicto"] == "YES" and e["confianza"] == "alta" and "uefa" in e["fuente_2"] and "UEFA:" in e["resultado"]
    e = cruce.resolver_accesorio(m, {"jugador": "Kvaratskhelia"}, "titular", partido, espn, tsdb)
    assert e["veredicto"] == "NO"
    e = cruce.resolver_accesorio(m, {"jugador": "Dembélé"}, "gol", partido, espn, tsdb)
    assert e["veredicto"] == "YES"
    # sin gol y titular en ambas → NO
    e = cruce.resolver_accesorio(m, {"jugador": "Fabián Ruiz"}, "gol", partido, espn, tsdb)
    assert e["veredicto"] == "NO"
    # sin gol y en la banca: participación no confirmada por las dos → escalado con sugerencia CANCELAR (no entró según ESPN)
    e = cruce.resolver_accesorio(m, {"jugador": "Kvaratskhelia"}, "gol", partido, espn, tsdb)
    assert e["escalar"] and e["veredicto_sugerido"] == "CANCELAR" and "participación" in e["razon"]
    # entró de cambio según ESPN → sugerido NO, sigue escalado
    espn2 = {**espn, "cambios": ["Khvicha Kvaratskhelia"]}
    e = cruce.resolver_accesorio(m, {"jugador": "Kvaratskhelia"}, "gol", partido, espn2, tsdb)
    assert e["escalar"] and e["veredicto_sugerido"] == "NO"
    # no convocado en ambas → CANCELAR con confianza alta
    e = cruce.resolver_accesorio(m, {"jugador": "Victor Osimhen"}, "gol", partido, {**espn, "cambios": []}, tsdb)
    assert e["veredicto"] == "CANCELAR" and e["confianza"] == "alta"
    # discrepancia → escalado; sin TSDB → escalado con sugerencia
    tsdb2 = _resumen(["Khvicha Kvaratskhelia"], [], url="https://www.uefa.com/uefachampionsleague/match/1/")
    e = cruce.resolver_accesorio(m, {"jugador": "Kvaratskhelia"}, "titular", partido, espn, tsdb2)
    assert e["escalar"] and "discrepan" in e["razon"]
    # TheSportsDB (recortada) solo confirma presencias: YES titular sí, NO/CANCELAR no
    recortada = _resumen(["Fabian Ruiz"], [], url="https://www.thesportsdb.com/event/1", completo=False)
    assert cruce.resolver_accesorio(m, {"jugador": "Fabián Ruiz"}, "titular", partido, espn, recortada)["veredicto"] == "YES"
    e = cruce.resolver_accesorio(m, {"jugador": "Kvaratskhelia"}, "titular", partido, espn, recortada)
    assert e["escalar"] and e["veredicto_sugerido"] == "NO" and "solo confirma presencias" in e["razon"]
    e = cruce.resolver_accesorio(m, {"jugador": "Victor Osimhen"}, "gol", partido, {**espn, "cambios": []}, recortada)
    assert e["escalar"] and "solo confirma presencias" in e["razon"]
    e = cruce.resolver_accesorio(m, {"jugador": "Fabián Ruiz"}, "titular", partido, espn, None)
    assert e["escalar"] and e["veredicto_sugerido"] == "YES" and "una sola fuente" in e["razon"]


def test_tsdb_resumen_parseo():
    from app.services.resolucion import fuentes

    class FakeHttp:
        def get(self, url):
            if "lookuplineup" in url:
                return {"lineup": [
                    {"strPlayer": "Virgil van Dijk", "strTeam": "Liverpool", "strSubstitute": "No"},
                    {"strPlayer": "Federico Chiesa", "strTeam": "Liverpool", "strSubstitute": "Yes"},
                    {"strPlayer": "Sam Morsy", "strTeam": "Ipswich Town", "strSubstitute": "No"},
                ]}
            return {"timeline": [
                {"strTimeline": "Goal", "strTimelineDetail": "Normal Goal", "strPlayer": "Alexander Isak", "strTeam": "Liverpool", "intTime": "6"},
                {"strTimeline": "Card", "strTimelineDetail": "Yellow Card", "strPlayer": "X", "strTeam": "Liverpool", "intTime": "30"},
                {"strTimeline": "Goal", "strTimelineDetail": "Own Goal", "strPlayer": "Sam Morsy", "strTeam": "Liverpool", "intTime": "70"},
            ]}

    r = fuentes.tsdb_resumen(FakeHttp(), "2494027")
    assert r["equipos"]["Liverpool"] == {"titulares": ["Virgil van Dijk"], "banca": ["Federico Chiesa"]}
    assert [g["jugador"] for g in r["goles"]] == ["Alexander Isak", "Sam Morsy"] and r["goles"][1]["tipo"] == "Own Goal"
    assert r["cambios"] is None and r["url"].endswith("/event/2494027")
    assert cruce.sugerir_gol("Isak", r)[0] == "YES"
    assert cruce.sugerir_gol("Morsy", r)[0] == "NO"  # el autogol no cuenta
    assert cruce.sugerir_titular("Chiesa", r)[0] == "NO"


# ── props NFL con doble fuente (ESPN + CBS) ──────────────────────────────────

def test_cbs_url_y_parseo():
    from pathlib import Path
    from app.services.resolucion import fuentes
    # kickoff 00:35 UTC del 11-sep = 20:35 del 10-sep en el este → fecha 20260910
    k = datetime(2026, 9, 11, 0, 35, tzinfo=timezone.utc)
    assert fuentes.cbs_url_boxscore(k, "SF", "LAR") == "https://www.cbssports.com/nfl/gametracker/boxscore/NFL_20260910_SF@LAR/"
    assert "NFL_20260910_WAS@JAC/" in fuentes.cbs_url_boxscore(k, "WSH", "JAX")
    html = Path(__file__).parent.joinpath("fixtures", "cbs_boxscore_min.html").read_text()
    bs = fuentes.parsear_cbs_boxscore(html, "u")
    j = bs["jugadores"]
    assert set(j) == {"Matthew Stafford", "Christian Mccaffrey", "Jaxon Smith Njigba"}  # la defensa no entra
    assert j["Matthew Stafford"]["passing"] == {"passingYards": "155", "passingTouchdowns": "0", "interceptions": "1"} and j["Matthew Stafford"]["equipo"] == "LAR"
    assert j["Christian Mccaffrey"]["rushing"]["rushingYards"] == "68" and j["Christian Mccaffrey"]["receiving"]["receivingYards"] == "20"
    assert j["Jaxon Smith Njigba"]["receiving"]["receivingTouchdowns"] == "1"
    assert cruce._persona_coincide("Jaxon Smith-Njigba", "Jaxon Smith Njigba")
    assert cruce.fantasy_estandar(j["Christian Mccaffrey"])[0] == 8.8


def test_resolver_prop_nfl():
    partido = P("Los Angeles Rams", "San Francisco 49ers", 7, 27)
    m = {"id": "x"}
    espn = {"url": "https://www.espn.com/nfl/boxscore/_/gameId/1", "jugadores": {
        "Christian McCaffrey": {"rushing": {"rushingYards": "68", "rushingTouchdowns": "0"}, "receiving": {"receivingYards": "20", "receivingTouchdowns": "0"}, "fumbles": {"fumblesLost": "0"}}}}
    cbs = {"url": "https://www.cbssports.com/x", "jugadores": {
        "Christian Mccaffrey": {"rushing": {"rushingYards": "68", "rushingTouchdowns": "0"}, "receiving": {"receivingYards": "20", "receivingTouchdowns": "0"}}}}
    td = {"jugador": "Christian McCaffrey", "tipo": "td", "umbral": 1}
    fan = {"jugador": "Christian McCaffrey", "tipo": "fantasy", "umbral": 15}
    e = cruce.resolver_prop_nfl(m, td, partido, espn, cbs, "Christian McCaffrey", "Christian Mccaffrey")
    assert e["veredicto"] == "NO" and e["confianza"] == "alta" and e["fuente_2"] == "https://www.cbssports.com/x"
    assert cruce.resolver_prop_nfl(m, fan, partido, espn, cbs, "Christian McCaffrey", "Christian Mccaffrey")["veredicto"] == "NO"
    # fumble perdido según ESPN → escalado (CBS no lo publica)
    espn_f = {**espn, "jugadores": {"Christian McCaffrey": {**espn["jugadores"]["Christian McCaffrey"], "fumbles": {"fumblesLost": "1"}}}}
    e = cruce.resolver_prop_nfl(m, fan, partido, espn_f, cbs, "Christian McCaffrey", "Christian Mccaffrey")
    assert e["escalar"] and "balón suelto" in e["razon"]
    # discrepancia
    cbs_d = {"url": "u", "jugadores": {"Christian Mccaffrey": {"rushing": {"rushingTouchdowns": "1"}}}}
    e = cruce.resolver_prop_nfl(m, td, partido, espn, cbs_d, "Christian McCaffrey", "Christian Mccaffrey")
    assert e["escalar"] and "discrepan" in e["razon"]
    # inactivo en ambos → CANCELAR alta; ausente en uno → escalado; sin CBS → escalado con sugerencia
    e = cruce.resolver_prop_nfl(m, td, partido, espn, cbs, None, None)
    assert e["veredicto"] == "CANCELAR" and e["confianza"] == "alta"
    e = cruce.resolver_prop_nfl(m, td, partido, espn, cbs, "Christian McCaffrey", None)
    assert e["escalar"] and "no en el de CBS" in e["razon"]
    e = cruce.resolver_prop_nfl(m, td, partido, espn, None, "Christian McCaffrey", None)
    assert e["escalar"] and e["veredicto_sugerido"] == "NO" and "CBS no respondió" in e["razon"]


def test_uefa_partidos_resumen_y_emparejar():
    from app.services.resolucion import fuentes

    class FakeHttp:
        def get(self, url):
            if "/lineups" in url:
                return {"homeTeam": {"team": {"internationalName": "Paris"}, "field": [{"player": {"internationalName": "Fabián Ruiz"}}] * 11,
                                     "bench": [{"player": {"internationalName": "Khvicha Kvaratskhelia"}}]},
                        "awayTeam": {"team": {"internationalName": "S. Bratislava"}, "field": [{"player": {"internationalName": "X"}}], "bench": []}}
            return [{"id": "2049559", "kickOffTime": {"dateTime": "2026-09-09T19:00:00Z"}, "status": "FINISHED",
                     "homeTeam": {"internationalName": "Paris", "translations": {"displayOfficialName": {"EN": "Paris Saint-Germain"}}},
                     "awayTeam": {"internationalName": "S. Bratislava", "translations": {"displayOfficialName": {"EN": "Slovan Bratislava"}}},
                     "score": {"total": {"home": 6, "away": 1}},
                     "playerEvents": {"scorers": [{"goalType": "SCORED", "time": {"minute": 17}, "player": {"internationalName": "Ousmane Dembélé"}},
                                                  {"goalType": "OWN_GOAL", "time": {"minute": 58}, "player": {"internationalName": "Sekou Camara"}}]}}]

    http = FakeHttp()
    lista = fuentes.uefa_partidos(http, "Champions League", datetime(2026, 9, 9, tzinfo=timezone.utc), datetime(2026, 9, 9, tzinfo=timezone.utc))
    assert lista[0]["home"] == ["Paris", "Paris Saint-Germain"] and lista[0]["home_score"] == 6
    espn = P("Paris Saint-Germain", "Slovan Bratislava", 6, 1, dt=datetime(2026, 9, 9, 19, 0, tzinfo=timezone.utc))
    u = cruce.emparejar_uefa(espn, lista)
    assert u is not None and u["id"] == "2049559"
    assert cruce.emparejar_uefa(P("Liverpool", "Atlético Madrid", dt=espn.kickoff), lista) is None
    r = fuentes.uefa_resumen(http, "Champions League", u)
    assert r["completo"] is True and len(r["equipos"]["Paris"]["titulares"]) == 11 and r["url"] == "https://www.uefa.com/uefachampionsleague/match/2049559/"
    assert cruce.sugerir_gol("Dembélé", r)[0] == "YES" and cruce.sugerir_gol("Camara", r)[0] == "NO"  # autogol no cuenta
    assert cruce.sugerir_titular("Kvaratskhelia", r)[0] == "NO"
