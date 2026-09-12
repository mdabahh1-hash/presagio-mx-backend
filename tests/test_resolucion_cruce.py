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
