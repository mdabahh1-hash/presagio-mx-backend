"""Cruce mercado ↔ partido y veredicto mecánico (resolucion/cruce.py). Sin red:
los accesorios de jugador usan respuestas reales recortadas (tests/fixtures)
servidas por FakeHttp."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.resolucion import cruce, fuentes, plan
from app.services.resolucion.fuentes import AET, FT, NFL_CATEGORIAS_OFENSIVAS, POSTPONED, SCHEDULED, Partido
from app.services.resolucion.sujeto import errores_identidad
from app.services.resolucion.validar import validar_entrada
from tests.fakes import FakeHttp, fixture_json, fixture_texto

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
    # redacción corta: solo el rival
    assert cruce.parse_titular({"question": "¿Rayan Cherki será titular ante Porto?"}) == \
        {"jugador": "Rayan Cherki", "equipos": ["Porto"]}


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


# ── nombre de persona: solo chequeo de cordura junto a un id ─────────────────

@pytest.mark.parametrize("a,b,esperado", [
    ("Federico Dimarco", "Federico Valverde", False), ("Álvaro Fidalgo", "Álvaro Valles", False),
    ("Julián Álvarez", "Julian Alvarez", True), ("Cherki", "Rayan Cherki", True),
    ("Mateo Kovačić", "Mateo Kovacic", True), ("Rodri", "Rodri", True), ("Rodri", "Rodrigo Hernández", False),
    ("Fabián Ruiz", "Fabian Ruiz Peña", True), ("Kylian Mbappé", "Kylian Mbappe", True),
    ("Kylian Mbappé", "Ethan Mbappé", False), ("Víctor Guzmán", "Victor Guzman", True),
    # por eso el nombre nunca localiza a nadie: subconjuntos que son otra persona
    ("Josh Allen", "Josh Hines-Allen", True), ("Silva", "Bernardo Silva", True),
])
def test_persona_coincide(a, b, esperado):
    assert cruce._persona_coincide(a, b) is esperado


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


def test_college_football_va_por_la_ruta_nfl():
    # nombre corto de escuela (label/TSDB) contra el displayName de ESPN, con otro Texas el mismo día
    assert fuentes.deporte("College Football") == "nfl"
    assert "college-football/game" in fuentes._url_partido("College Football", "401")
    tex = P("Tennessee Volunteers", "Texas Longhorns", 24, 31, id="1")
    otro = P("LSU Tigers", "Texas A&M Aggies", 20, 17, id="2")
    p, nota = cruce.emparejar_cualquier_sede(["Tennessee", "Texas"], K, [otro, tex])
    assert p is tex and nota == ""
    outs = [("tennessee", "Tennessee"), ("texas", "Texas")]
    e = cruce.resolver_ganador({"id": "x"}, outs, tex, "", P("Tennessee", "Texas", 24, 31, fuente="tsdb"))
    assert e["veredicto"] == "texas" and e["confianza"] == "alta"


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


@pytest.mark.parametrize("q,esperado", [
    # redacción corta (plantilla desde 2026-09-22): nombre completo, N+ y TD
    ("¿Jaxon Smith-Njigba anotará 1+ TD en la Semana 3?", {"jugador": "Jaxon Smith-Njigba", "tipo": "td", "umbral": 1.0}),
    ("¿Drake Maye lanzará 2+ pases de TD en la Semana 3?", {"jugador": "Drake Maye", "tipo": "pases_td", "umbral": 2.0}),
    ("¿Christian McCaffrey conseguirá 15.5+ puntos de fantasy en la Semana 3?",
     {"jugador": "Christian McCaffrey", "tipo": "fantasy", "umbral": 15.5}),
    # un «(ABC)» final no es parte del nombre (la plantilla ya no lo lleva, pero se tolera)
    ("¿Josh Allen (BUF) anotará 1+ TD en la Semana 1?", {"jugador": "Josh Allen", "tipo": "td", "umbral": 1.0}),
    # mezclas de las dos redacciones
    ("¿Drake Maye lanzará 2 o más pases de TD en la Semana 3?", {"jugador": "Drake Maye", "tipo": "pases_td", "umbral": 2.0}),
    ("¿Travis Kelce anotará 1+ touchdown en la Semana 3?", {"jugador": "Travis Kelce", "tipo": "td", "umbral": 1.0}),
    # un número suelto no dice si es "al menos": no se adivina, se escala
    ("¿Travis Kelce anotará 1 TD en la Semana 3?", None),
    ("¿Drake Maye lanzará 2 pases de TD en la Semana 3?", None),
])
def test_parse_prop_nfl_redaccion_corta(q, esperado):
    assert cruce.parse_prop_nfl({"question": q}) == esperado


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
    # presente solo en defensa: sin tabla ofensiva → td sin sugerencia, pases/fantasy NO
    defensa = {"defensive": {"totalTackles": "5"}}
    assert cruce.sugerir_prop_nfl({"tipo": "td", "umbral": 1}, defensa)[0] is None
    assert cruce.sugerir_prop_nfl({"tipo": "pases_td", "umbral": 2}, defensa)[0] == "NO"
    assert cruce.sugerir_prop_nfl({"tipo": "fantasy", "umbral": 15}, defensa)[0] == "NO"


def test_cbs_url_y_parseo():
    # kickoff 00:35 UTC del 11-sep = 20:35 del 10-sep en el este → fecha 20260910
    k = datetime(2026, 9, 11, 0, 35, tzinfo=timezone.utc)
    assert fuentes.cbs_url_boxscore(k, "SF", "LAR") == "https://www.cbssports.com/nfl/gametracker/boxscore/NFL_20260910_SF@LAR/"
    assert "NFL_20260910_WAS@JAC/" in fuentes.cbs_url_boxscore(k, "WSH", "JAX")
    bs = fuentes.parsear_cbs_boxscore(fixture_texto("cbs_boxscore_min.html"), "u")
    j = bs["jugadores"]
    assert set(j) == {"1114942", "2136743", "3115302", "9"}  # por id de CBS; la defensa cuenta como presencia
    assert j["1114942"]["passing"] == {"passingYards": "155", "passingTouchdowns": "0", "interceptions": "1"}
    assert (j["1114942"]["abbr"], j["1114942"]["slug"], j["1114942"]["nombre"]) == ("LAR", "matthew-stafford", "Matthew Stafford")
    assert j["2136743"]["rushing"]["rushingYards"] == "68" and j["2136743"]["receiving"]["receivingYards"] == "20"
    assert j["2136743"]["secciones"] == ["rushing", "receiving"]
    assert j["3115302"]["receiving"]["receivingTouchdowns"] == "1"
    # fred-warner: presente (Defense) pero fuera de las stats de props
    assert j["9"]["secciones"] == ["defense"] and not any(c in j["9"] for c in NFL_CATEGORIAS_OFENSIVAS)
    assert cruce._persona_coincide("Jaxon Smith-Njigba", "Jaxon Smith Njigba")
    assert cruce.fantasy_estandar(j["2136743"])[0] == 8.8
    # captura real recortada (BUF@HOU): devoluciones también cuentan como presencia
    real = fuentes.parsear_cbs_boxscore(fixture_texto("cbs_BUF_HOU_min.html"), "u")["jugadores"]
    assert real["2181054"]["abbr"] == "BUF" and real["2181054"]["passing"]["passingTouchdowns"] == "2"
    assert real["2223207"]["secciones"] == ["kickoff returns", "punt returns"]
    assert not any(c in real["2223207"] for c in NFL_CATEGORIAS_OFENSIVAS)


# ── props NFL: Semana 1 de 2026 con respuestas reales recortadas ─────────────

K_W1 = datetime(2026, 9, 13, 17, 0, tzinfo=timezone.utc)
AHORA_W1 = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)
SUJETO_ALLEN = {"jugador": "Josh Allen", "equipo": "Bills", "rival": "Texans", "posicion": "QB", "alcance": "partido",
                "ids": {"espn": "3918298", "cbs": "2181054"}}
SUJETO_LAMAR = {"jugador": "Lamar Jackson", "equipo": "Ravens", "rival": "Colts", "posicion": "QB", "alcance": "partido",
                "ids": {"espn": "3916387", "cbs": "2181169"}}
SUJETO_HINES = {"jugador": "Josh Hines-Allen", "equipo": "Jaguars", "rival": "Browns", "posicion": "DE",
                "alcance": "partido", "ids": {"espn": "3915239", "cbs": "2184628"}}
PASES_2 = {"jugador": "Josh Allen", "tipo": "pases_td", "umbral": 2.0}


def http_nfl() -> FakeHttp:
    """Scoreboard y summaries de ESPN + box scores de CBS de la Semana 1."""
    nfl = fixture_json("nfl_w1_espn_min.json")
    return FakeHttp(
        {"football/nfl/scoreboard": nfl["scoreboard"], **{f"summary?event={ev}": d for ev, d in nfl["summary"].items()}},
        {f"NFL_20260913_{par}/": fixture_texto(f"cbs_{par.replace('@', '_')}_min.html")
         for par in ("BUF@HOU", "BAL@IND", "CLE@JAC")},
    )


def prop(id_, pregunta, sujeto):
    return {"id": id_, "question": pregunta, "category": "Deportes", "subcategory": "NFL", "market_type": "binary",
            "kind": "accesorio", "status": "pending_resolution", "ends_at": "2026-09-13T17:00:00Z", "sujeto": sujeto,
            "volume": 0, "num_trades": 0}


def partido_w1(http: FakeHttp, event_id: str) -> Partido:
    return next(p for p in fuentes.espn_scoreboard(http, "NFL", K_W1, K_W1) if p.id == event_id)


def test_regresion_allen_partido_por_equipo_y_jugador_por_id():
    """Semana 1: el scoreboard lista CLE@JAX (Josh Hines-Allen) antes que BUF@HOU.
    El resolvedor viejo tomaba el primer box score con un nombre "parecido" y
    sugirió NO con las stats del DE de los Jaguars."""
    http = http_nfl()
    mercados = [
        prop("nfl-allen-2tdpass-w1-2026", "¿Josh Allen lanzará 2 o más pases de touchdown en la Semana 1?", SUJETO_ALLEN),
        prop("nfl-allen-fantasy15-w1-2026", "¿Josh Allen conseguirá 15 o más puntos de fantasy en la Semana 1?", SUJETO_ALLEN),
        prop("nfl-lamar-fantasy15-w1-2026", "¿Lamar Jackson conseguirá 15 o más puntos de fantasy en la Semana 1?", SUJETO_LAMAR),
        prop("nfl-allen-sin-sujeto", "¿Josh Allen lanzará 2 o más pases de touchdown en la Semana 1?", None),
        prop("nfl-allen-td-temporada", "¿Josh Allen anotará al menos 10 touchdowns en la temporada?",
             {**SUJETO_ALLEN, "alcance": "temporada", "rival": ""}),
    ]
    r = plan.armar_plan(mercados, http=http)
    res = {e["id"]: e for e in r["resoluciones"]}
    esc = {e["id"]: e for e in r["escalados"]}

    # nunca se consulta el partido del homónimo
    assert not [u for u in http.urls if "401872922" in u or "CLE@JAC" in u]
    assert fuentes.espn_scoreboard(http, "NFL", K_W1, K_W1)[0].id == "401872922"  # y eso que va primero

    assert set(res) == {"nfl-allen-2tdpass-w1-2026", "nfl-allen-fantasy15-w1-2026"}
    for mid, e in res.items():
        assert e["veredicto"] == "YES" and e["confianza"] == "alta"
        assert "gameId/401872660" in e["fuente_1"] and "NFL_20260913_BUF@HOU" in e["fuente_2"]
        sc = e["sujeto_confirmado"]
        assert (sc["jugador"], sc["equipo"], sc["partido"]) == ("Josh Allen", "Buffalo Bills", "BUF@HOU")
        assert (sc["espn"]["id"], sc["cbs"]["id"]) == ("3918298", "2181054")
        detalle = next(m for m in mercados if m["id"] == mid)
        # la salida del resolvedor pasa la defensa en profundidad tal cual
        assert errores_identidad(detalle, e) == [] and validar_entrada(e, detalle, AHORA_W1) == []
    assert "2 pases de TD" in res["nfl-allen-2tdpass-w1-2026"]["resultado"]
    assert "35.66 pts" in res["nfl-allen-fantasy15-w1-2026"]["resultado"]

    lamar = esc["nfl-lamar-fantasy15-w1-2026"]  # 1 fumble perdido: 24.96 (26.96 sin él)
    assert lamar["veredicto_sugerido"] == "YES" and "confianza" not in lamar and "balón suelto" in lamar["razon"]
    assert "24.96" in lamar["resultado"] and lamar["sujeto_confirmado"]["espn"]["id"] == "3916387"

    sin = esc["nfl-allen-sin-sujeto"]
    assert "sin sujeto" in sin["razon"] and "veredicto_sugerido" not in sin
    # la misma entrada escrita a mano sobre el mercado sin sujeto: validar_entrada la rechaza
    manual = {**res["nfl-allen-2tdpass-w1-2026"], "id": "nfl-allen-sin-sujeto"}
    assert any("sin sujeto" in x for x in validar_entrada(manual, mercados[3], AHORA_W1))

    temporada = esc["nfl-allen-td-temporada"]
    assert "alcance 'temporada'" in temporada["razon"] and "veredicto_sugerido" not in temporada


def test_sujeto_con_equipo_equivocado_nunca_usa_al_homonimo():
    """Si el sujeto se cargó con los Jaguars, el partido es CLE@JAX pero el id de
    Allen no está: nada de YES/NO con las stats de Hines-Allen, nunca alta."""
    m = prop("nfl-allen-td-w1-2026", "¿Josh Allen anotará al menos 1 touchdown en la Semana 1?",
             {**SUJETO_ALLEN, "equipo": "Jaguars", "rival": "Browns"})
    r = plan.armar_plan([m], http=http_nfl())
    assert r["resoluciones"] == []
    e = r["escalados"][0]
    assert "gameId/401872922" in e["fuente_1"] and e.get("veredicto_sugerido") in (None, "CANCELAR")
    assert "Hines" not in e["resultado"] and "espn" not in e["sujeto_confirmado"]


def test_espn_boxscore_nfl_por_id_con_todas_las_categorias():
    http = http_nfl()
    jax = fuentes.espn_boxscore_nfl(http, "NFL", "401872922")
    hines = jax["jugadores"]["3915239"]
    assert (hines["nombre"], hines["abbr"], hines["equipo"]) == ("Josh Hines-Allen", "JAX", "Jacksonville Jaguars")
    assert {"defensive", "fumbles"} <= set(hines) and not any(c in hines for c in NFL_CATEGORIAS_OFENSIVAS)
    assert jax["estado"] == FT and jax["injuries"]["JAX"] == [{"id": "4432773", "nombre": "Brian Thomas Jr.", "estado": "Questionable"}]
    buf = fuentes.espn_boxscore_nfl(http, "NFL", "401872660")
    allen = buf["jugadores"]["3918298"]
    assert allen["passing"]["passingTouchdowns"] == "2" and allen["fumbles"]["fumblesLost"] == "0"
    assert cruce.fantasy_estandar(allen)[0] == 35.66 and "3915239" not in buf["jugadores"]
    assert buf["equipos"] == {"BUF": "Buffalo Bills", "HOU": "Houston Texans"}


def test_localizar_jugador_y_lado_del_equipo():
    http = http_nfl()
    p = partido_w1(http, "401872660")
    assert cruce.lado_del_equipo(p, "Bills") == {"lado": "away", "nombre": "Buffalo Bills", "abbr": "BUF",
                                                 "rival": "Houston Texans", "rival_abbr": "HOU"}
    assert cruce.lado_del_equipo(P("New York Jets", "New York Giants"), "New York") is None  # ambiguo
    assert cruce.lado_del_equipo(p, "Bengals") is None

    buf = fuentes.espn_boxscore_nfl(http, "NFL", "401872660")
    assert cruce.localizar_jugador(buf, SUJETO_ALLEN, "espn", "BUF")["estado"] == "ok"
    lesionado = cruce.localizar_jugador(buf, {"jugador": "Ty Johnson", "ids": {"espn": "3915411"}}, "espn", "BUF")
    assert lesionado["estado"] == "ausente" and "reporte de lesiones de ESPN: Out" in lesionado["nota"]
    # en el box score de los Jaguars "Josh Allen" no es "Josh Hines-Allen": ausente, no ok
    jax = fuentes.espn_boxscore_nfl(http, "NFL", "401872922")
    assert cruce.localizar_jugador(jax, SUJETO_ALLEN, "espn", "JAX")["estado"] == "ausente"
    cle_jac = fuentes.cbs_boxscore_nfl(http, K_W1, "CLE", "JAX")
    assert cruce.localizar_jugador(cle_jac, SUJETO_ALLEN, "cbs", "JAX")["estado"] == "ausente"
    # el mismo id visto desde el rival → otro_equipo; CBS escribe JAC y ESPN JAX: mismo equipo
    assert cruce.localizar_jugador(jax, SUJETO_HINES, "espn", "CLE")["estado"] == "otro_equipo"
    assert cruce.localizar_jugador(cle_jac, SUJETO_HINES, "cbs", "JAX")["estado"] == "ok"


# Tabla de verdad con box scores armados a mano (misma forma que los parsers).
PARTIDO_W1 = P("Houston Texans", "Buffalo Bills", 31, 36, dt=K_W1, id="401872660",
               alias=["Houston Texans", "Texans", "Texans", "HOU", "|", "Buffalo Bills", "Bills", "Bills", "BUF"])
ALLEN_E = {"id": "3918298", "nombre": "Josh Allen", "abbr": "BUF", "fumbles": {"fumblesLost": "0"},
           "passing": {"passingYards": "334", "passingTouchdowns": "2", "interceptions": "0"},
           "rushing": {"rushingYards": "23", "rushingTouchdowns": "2"}}
ALLEN_C = {"id": "2181054", "nombre": "Josh Allen", "abbr": "BUF", "secciones": ["passing", "rushing"],
           "passing": {"passingYards": "334", "passingTouchdowns": "2", "interceptions": "0"},
           "rushing": {"rushingYards": "23", "rushingTouchdowns": "2"}}
COOK_E = {"id": "4379399", "nombre": "James Cook III", "abbr": "BUF", "rushing": {"rushingYards": "57", "rushingTouchdowns": "0"}}
COOK_C = {"id": "2975698", "nombre": "James Cook", "abbr": "BUF", "secciones": ["rushing"],
          "rushing": {"rushingYards": "57", "rushingTouchdowns": "0"}}


def resolver_prop_manual(spec, espn_filas, cbs_filas, ids=None):
    sujeto = {**SUJETO_ALLEN, "ids": ids or SUJETO_ALLEN["ids"]}
    espn = None if espn_filas is None else {"url": "https://www.espn.com/nfl/boxscore/_/gameId/401872660",
                                            "jugadores": {f["id"]: f for f in espn_filas}, "injuries": {}}
    cbs = None if cbs_filas is None else {"url": "https://www.cbssports.com/nfl/gametracker/boxscore/NFL_20260913_BUF@HOU/",
                                          "jugadores": {f["id"]: f for f in cbs_filas}}
    lado = cruce.lado_del_equipo(PARTIDO_W1, "Bills")
    loc_e = cruce.localizar_jugador(espn, sujeto, "espn", lado["abbr"])
    loc_c = cruce.localizar_jugador(cbs, sujeto, "cbs", lado["abbr"])
    e = cruce.resolver_prop_nfl({"id": "nfl-allen-2tdpass-w1-2026"}, spec, sujeto, PARTIDO_W1, lado, espn, cbs, loc_e, loc_c)
    return e, (loc_e["estado"], loc_c["estado"])


@pytest.mark.parametrize("espn_filas,cbs_filas,ids,estados,veredicto,sugerido", [
    ([ALLEN_E, COOK_E], [ALLEN_C, COOK_C], None, ("ok", "ok"), "YES", None),
    ([ALLEN_E], [{**ALLEN_C, "abbr": "?"}], None, ("ok", "ok"), "YES", None),                  # CBS sin equipo publicado
    ([ALLEN_E], None, None, ("ok", "caida"), None, None),                                      # CBS caído
    ([COOK_E], [COOK_C], None, ("ausente", "ausente"), None, "CANCELAR"),                      # nunca alta
    ([ALLEN_E], [COOK_C], None, ("ok", "ausente"), None, None),
    ([COOK_E], [ALLEN_C], None, ("ausente", "ok"), None, None),
    ([ALLEN_E], [ALLEN_C], {"espn": "3918298"}, ("ok", "sin_id"), None, None),
    ([{**ALLEN_E, "abbr": "JAX"}], [ALLEN_C], None, ("otro_equipo", "ok"), None, None),
    ([ALLEN_E, COOK_E], [ALLEN_C], {"espn": "4379399", "cbs": "2181054"}, ("discrepa", "ok"), None, None),  # id de otro
    ([ALLEN_E], [ALLEN_C], {"espn": "3915239", "cbs": "2181054"}, ("discrepa", "ok"), None, None),  # id equivocado
], ids=["ok-ok", "cbs-abbr-?", "cbs-caida", "ausente-ambas", "solo-espn", "solo-cbs", "sin-id", "otro-equipo",
        "id-de-otra-persona", "id-equivocado"])
def test_tabla_de_verdad_prop_nfl(espn_filas, cbs_filas, ids, estados, veredicto, sugerido):
    e, locs = resolver_prop_manual(PASES_2, espn_filas, cbs_filas, ids)
    assert locs == estados
    if veredicto:
        assert e["veredicto"] == veredicto and e["confianza"] == "alta" and "escalar" not in e
        assert set(e["sujeto_confirmado"]) >= {"espn", "cbs"}
        return
    assert e["escalar"] and "confianza" not in e and "veredicto" not in e
    assert e.get("veredicto_sugerido") == sugerido
    assert "ESPN:" in e["razon"] and "CBS:" in e["razon"]  # la razón lleva las notas de las dos fuentes
    if sugerido == "CANCELAR":
        assert "no publica la lista de inactivos" in e["razon"]
    # un bloque por fuente solo con identidad ok
    assert {"espn", "cbs"} & set(e["sujeto_confirmado"]) == {f for f, s in zip(("espn", "cbs"), estados) if s == "ok"}


def test_prop_nfl_fuentes_discrepan_sugiere_espn():
    cbs_1td = {**ALLEN_C, "passing": {**ALLEN_C["passing"], "passingTouchdowns": "1"}}
    e, _ = resolver_prop_manual(PASES_2, [ALLEN_E], [cbs_1td])
    assert e["escalar"] and e["veredicto_sugerido"] == "YES" and "discrepan" in e["razon"]


def test_fantasy_cerca_del_umbral_o_con_fumble_escala():
    fan = {"jugador": "Josh Allen", "tipo": "fantasy", "umbral": 15.0}

    def qb(yardas, fumbles="0"):
        pase = {"passingYards": str(yardas), "passingTouchdowns": "0", "interceptions": "0"}
        return ({**ALLEN_E, "passing": pase, "rushing": {}, "fumbles": {"fumblesLost": fumbles}},
                {**ALLEN_C, "passing": pase, "rushing": {}})

    e_, c_ = qb(275)  # 11.00 pts: a 4 del umbral (conversiones de 2 pts no vienen en el box score)
    e, _ = resolver_prop_manual(fan, [e_], [c_])
    assert e["escalar"] and e["veredicto_sugerido"] == "NO" and "conversiones de 2 pts" in e["razon"]
    e_, c_ = qb(272)  # 10.88 pts: a más de 4 → NO alta
    e, _ = resolver_prop_manual(fan, [e_], [c_])
    assert e["veredicto"] == "NO" and e["confianza"] == "alta"
    e_, c_ = qb(500, fumbles="1")  # 18 pts con el fumble; CBS no publica fumbles
    e, _ = resolver_prop_manual(fan, [e_], [c_])
    assert e["escalar"] and e["veredicto_sugerido"] == "YES" and "balón suelto" in e["razon"]


def test_presente_solo_en_defensa_o_devoluciones():
    http = http_nfl()
    partido = partido_w1(http, "401872922")
    lado = cruce.lado_del_equipo(partido, "Jaguars")
    jax = fuentes.espn_boxscore_nfl(http, "NFL", partido.id)
    cle_jac = fuentes.cbs_boxscore_nfl(http, partido.kickoff, "CLE", "JAX")
    loc_e = cruce.localizar_jugador(jax, SUJETO_HINES, "espn", lado["abbr"])
    loc_c = cruce.localizar_jugador(cle_jac, SUJETO_HINES, "cbs", lado["abbr"])
    assert (loc_e["estado"], loc_c["estado"]) == ("ok", "ok") and cle_jac["jugadores"]["2184628"]["secciones"] == ["defense"]
    m = {"id": "nfl-hines-prueba"}
    td = cruce.resolver_prop_nfl(m, {"jugador": "Josh Hines-Allen", "tipo": "td", "umbral": 1.0}, SUJETO_HINES,
                                 partido, lado, jax, cle_jac, loc_e, loc_c)
    assert td["escalar"] and "veredicto_sugerido" not in td and "sin jugada ofensiva" in td["razon"]
    pases = cruce.resolver_prop_nfl(m, {"jugador": "Josh Hines-Allen", "tipo": "pases_td", "umbral": 2.0}, SUJETO_HINES,
                                    partido, lado, jax, cle_jac, loc_e, loc_c)
    assert pases["escalar"] and pases["veredicto_sugerido"] == "NO" and "confianza" not in pases

    # devoluciones (Greg Dortch, BUF@HOU real): presente en ambas, sin jugada ofensiva
    buf_hou = partido_w1(http, "401872660")
    lado = cruce.lado_del_equipo(buf_hou, "Bills")
    dortch = {"jugador": "Greg Dortch", "equipo": "Bills", "rival": "Texans", "posicion": "WR", "alcance": "partido",
              "ids": {"espn": "4037235", "cbs": "2223207"}}
    buf = fuentes.espn_boxscore_nfl(http, "NFL", buf_hou.id)
    cbs = fuentes.cbs_boxscore_nfl(http, buf_hou.kickoff, "BUF", "HOU")
    loc_e = cruce.localizar_jugador(buf, dortch, "espn", "BUF")
    loc_c = cruce.localizar_jugador(cbs, dortch, "cbs", "BUF")
    e = cruce.resolver_prop_nfl(m, {"jugador": "Greg Dortch", "tipo": "td", "umbral": 1.0}, dortch, buf_hou, lado, buf, cbs, loc_e, loc_c)
    assert (loc_e["estado"], loc_c["estado"]) == ("ok", "ok") and e["escalar"] and "veredicto_sugerido" not in e


# ── fútbol: titular / gol con un "Silva" en cada equipo ──────────────────────

K_UCL = datetime(2026, 9, 16, 19, 0, tzinfo=timezone.utc)
UCL = {"id": "ucl-accesorio-prueba", "subcategory": "Champions League"}
BERNARDO = {"jugador": "Bernardo Silva", "equipo": "Manchester City", "rival": "FC Porto", "posicion": "M",
            "alcance": "partido", "ids": {"espn": "9100", "uefa": "250000"}}
SILVA_PORTO = {"jugador": "Silva", "equipo": "FC Porto", "rival": "Manchester City", "posicion": "F",
               "alcance": "partido", "ids": {"espn": "9200", "uefa": "250001"}}
SPEC_GOL = {"tipo": "gol", "jugador": "Bernardo Silva", "equipos": ["Porto"]}
SPEC_TITULAR = {"tipo": "titular", "jugador": "Bernardo Silva", "equipos": ["Manchester City", "FC Porto"]}


def http_futbol(uefa_partidos=None) -> FakeHttp:
    fut = fixture_json("futbol_silva_min.json")
    return FakeHttp({
        "soccer/uefa.champions/scoreboard": fut["scoreboard"],
        "summary?event=": fut["summary"],
        "/lineups": fut["uefa_lineups"],
        "match.uefa.com/v5/matches?": fut["uefa_partidos"] if uefa_partidos is None else uefa_partidos,
    })


def resumenes_ucl():
    http = http_futbol()
    partido = fuentes.espn_scoreboard(http, "Champions League", K_UCL, K_UCL)[0]
    espn = fuentes.espn_summary(http, "Champions League", partido.id)
    lista = fuentes.uefa_partidos(http, "Champions League", K_UCL, K_UCL)
    return partido, espn, fuentes.uefa_resumen(http, "Champions League", cruce.emparejar_uefa(partido, lista))


def tsdb(lineup, timeline=()):
    return fuentes.tsdb_resumen(FakeHttp({"lookuplineup": {"lineup": list(lineup)},
                                          "lookuptimeline": {"timeline": list(timeline)}}), "2494027")


def test_espn_summary_y_uefa_por_id_con_team_id_int_o_str():
    http = http_futbol()
    espn = fuentes.espn_summary(http, "Champions League", "401900001")
    assert set(espn["equipos"]) == {"382", "437"}  # team.id int (382) y str (437) → str
    assert espn["equipos"]["382"]["jugadores"]["9102"] == {"id": "9102", "nombre": "Phil Foden", "titular": False, "entro": True}
    # goleador = solo participants[0]; el asistente (Bernardo Silva) no figura
    assert [(g["jugador_id"], g["equipo_id"]) for g in espn["goles"]] == [("9200", "437"), ("9101", "382")]
    lista = fuentes.uefa_partidos(http, "Champions League", K_UCL, K_UCL)
    assert (lista[0]["home_id"], lista[0]["away_id"]) == ("52919", "50064")
    assert [(g["jugador_id"], g["equipo_id"], g["equipo"]) for g in lista[0]["goles"]] == \
        [("250001", "50064", "Porto"), ("250010", "52919", "Man City")]  # teamId de la fila, nunca clubId

    partido = fuentes.espn_scoreboard(http, "Champions League", K_UCL, K_UCL)[0]
    u = cruce.emparejar_uefa(partido, lista)
    assert u["id"] == "2049600"
    assert cruce.emparejar_uefa(partido, lista + [{**lista[0], "id": "2049601"}]) is None  # ambiguo
    assert cruce.emparejar_uefa(P("Liverpool", "Atlético Madrid", dt=K_UCL), lista) is None
    uefa = fuentes.uefa_resumen(http, "Champions League", u)
    assert set(uefa["equipos"]) == {"52919", "50064"} and uefa["completo"] and not uefa["publica_cambios"]
    assert uefa["equipos"]["52919"]["alias"][:2] == ["Man City", "Manchester City"]
    assert "250000" in uefa["equipos"]["52919"]["jugadores"]
    assert uefa["url"] == "https://www.uefa.com/uefachampionsleague/match/2049600/"
    assert cruce.equipo_en_resumen(uefa, ["Manchester City"]) == "52919"
    assert cruce.equipo_en_resumen(uefa, [], equipo_id=52919) == "52919"
    assert cruce.equipo_en_resumen(espn, ["Manchester City", "FC Porto"]) is None  # ambiguo


def test_gol_del_homonimo_rival_y_del_asistente_no_cuentan():
    partido, espn, uefa = resumenes_ucl()
    e = cruce.resolver_accesorio(UCL, SPEC_GOL, "gol", partido, espn, uefa, BERNARDO)
    assert e["veredicto"] == "NO" and e["confianza"] == "alta"  # titular en ambas y sin gol propio
    assert (e["sujeto_confirmado"]["espn"]["id"], e["sujeto_confirmado"]["uefa"]["id"]) == ("9100", "250000")
    k = cruce.equipo_en_resumen(espn, ["Manchester City"])
    loc = cruce.localizar_en_partido(espn, BERNARDO, "espn", k)
    assert loc["estado"] == "ok" and cruce.goles_del_jugador(espn, k, loc) == []  # asistió el gol de Haaland
    e = cruce.resolver_accesorio(UCL, {**SPEC_GOL, "jugador": "Silva"}, "gol", partido, espn, uefa, SILVA_PORTO)
    assert e["veredicto"] == "YES" and e["confianza"] == "alta"


def test_gol_no_con_lista_de_goles_incompleta_escala_sin_sugerencia():
    partido, espn, uefa = resumenes_ucl()

    def sin_id(resumen, equipo_id):
        return {**resumen, "goles": [{**g, "jugador_id": ""} if g["equipo_id"] == equipo_id else g for g in resumen["goles"]]}

    # ESPN: el gol del City sin id del goleador (participants[0] sin athlete.id)
    e = cruce.resolver_accesorio(UCL, SPEC_GOL, "gol", partido, sin_id(espn, "382"), uefa, BERNARDO)
    assert e["escalar"] and "veredicto_sugerido" not in e and "confianza" not in e and "sin id del goleador" in e["razon"]
    # UEFA sin goleadores publicados (scorers vacío) en un partido con goles
    e = cruce.resolver_accesorio(UCL, SPEC_GOL, "gol", partido, espn, {**uefa, "goles": []}, BERNARDO)
    assert e["escalar"] and "veredicto_sugerido" not in e and "UEFA publicó 0 goles" in e["razon"]
    # un gol del rival sin id no tapa nada del sujeto: NO alta
    e = cruce.resolver_accesorio(UCL, SPEC_GOL, "gol", partido, sin_id(espn, "437"), uefa, BERNARDO)
    assert e["veredicto"] == "NO" and e["confianza"] == "alta"
    # el YES por id no depende de que la lista esté completa
    e = cruce.resolver_accesorio(UCL, {**SPEC_GOL, "jugador": "Silva"}, "gol", partido, espn,
                                 {**uefa, "goles": uefa["goles"][:1]}, SILVA_PORTO)
    assert e["veredicto"] == "YES" and e["confianza"] == "alta"


def test_accesorio_otro_equipo_o_id_dudoso_sin_sugerencia():
    partido, espn, uefa = resumenes_ucl()
    mal = {**BERNARDO, "equipo": "FC Porto", "rival": "Manchester City"}
    k_porto = cruce.equipo_en_resumen(espn, ["FC Porto"])
    assert cruce.localizar_en_partido(espn, mal, "espn", k_porto)["estado"] == "otro_equipo"
    e = cruce.resolver_accesorio(UCL, SPEC_TITULAR, "titular", partido, espn, uefa, mal)
    assert e["escalar"] and "veredicto_sugerido" not in e and "aparece con" in e["razon"]
    e = cruce.resolver_accesorio(UCL, SPEC_TITULAR, "titular", partido, espn, uefa, {**BERNARDO, "ids": {"espn": "9100"}})
    assert e["escalar"] and "veredicto_sugerido" not in e and "no trae ids.uefa" in e["razon"]
    # id de UEFA equivocado con el nombre en la convocatoria → discrepa
    e = cruce.resolver_accesorio(UCL, SPEC_TITULAR, "titular", partido, espn, uefa, {**BERNARDO, "ids": {"espn": "9100", "uefa": "259999"}})
    assert e["escalar"] and "veredicto_sugerido" not in e and "¿id equivocado?" in e["razon"]
    assert "uefa" not in e["sujeto_confirmado"] and e["sujeto_confirmado"]["espn"]["id"] == "9100"


def test_accesorio_ausente_en_ambas_escala_con_sugerencia():
    partido, espn, uefa = resumenes_ucl()
    rodri = {**BERNARDO, "jugador": "Rodri", "ids": {"espn": "9999", "uefa": "259999"}}
    e = cruce.resolver_accesorio(UCL, {**SPEC_TITULAR, "jugador": "Rodri"}, "titular", partido, espn, uefa, rodri)
    assert e["escalar"] and e["veredicto_sugerido"] == "NO" and "confianza" not in e
    assert "partido identificado por equipo" in e["razon"]
    e = cruce.resolver_accesorio(UCL, {**SPEC_GOL, "jugador": "Rodri"}, "gol", partido, espn, uefa, rodri)
    assert e["escalar"] and e["veredicto_sugerido"] == "CANCELAR" and "confianza" not in e


def test_participacion_y_sugerencias_por_fuente():
    partido, espn, uefa = resumenes_ucl()
    k_e, k_u = cruce.equipo_en_resumen(espn, ["Manchester City"]), cruce.equipo_en_resumen(uefa, ["Manchester City"])
    foden = {**BERNARDO, "jugador": "Phil Foden", "ids": {"espn": "9102", "uefa": "250011"}}
    grealish = {**BERNARDO, "jugador": "Jack Grealish", "ids": {"espn": "9103", "uefa": "250012"}}
    rodri = {**BERNARDO, "jugador": "Rodri", "ids": {"espn": "9999", "uefa": "259999"}}

    def loc(s, fuente="espn"):
        return cruce.localizar_en_partido(espn if fuente == "espn" else uefa, s, fuente, k_e if fuente == "espn" else k_u)

    assert cruce.participo("Bernardo Silva", espn, k_e, loc(BERNARDO)) is True
    assert cruce.participo("Phil Foden", espn, k_e, loc(foden)) is True           # entró de cambio
    assert cruce.participo("Jack Grealish", espn, k_e, loc(grealish)) is False    # banca sin entrar (ESPN publica cambios)
    assert cruce.participo("Jack Grealish", uefa, k_u, loc(grealish, "uefa")) is None  # la UEFA no publica cambios
    assert cruce.participo("Rodri", espn, k_e, loc(rodri)) is False               # no convocado
    assert cruce.sugerir_titular("Bernardo Silva", espn, k_e, loc(BERNARDO))[0] == "YES"
    assert cruce.sugerir_titular("Phil Foden", uefa, k_u, loc(foden, "uefa"))[0] == "NO"
    assert cruce.sugerir_titular("Rodri", espn, k_e, loc(rodri))[0] == "NO"
    assert cruce.sugerir_gol("Jack Grealish", espn, k_e, cruce.localizar_en_partido(espn, grealish, "espn", None))[0] is None

    # titular NO en ambas con la UEFA (completa) → alta; gol NO sin participación confirmada por las dos → escalado
    e = cruce.resolver_accesorio(UCL, SPEC_TITULAR, "titular", partido, espn, uefa, foden)
    assert e["veredicto"] == "NO" and e["confianza"] == "alta"
    e = cruce.resolver_accesorio(UCL, SPEC_GOL, "gol", partido, espn, uefa, foden)
    assert e["escalar"] and e["veredicto_sugerido"] == "NO" and "no publica cambios" in e["razon"]
    e = cruce.resolver_accesorio(UCL, SPEC_GOL, "gol", partido, espn, uefa, grealish)
    assert e["escalar"] and e["veredicto_sugerido"] == "CANCELAR"


def test_tsdb_resumen_parseo():
    r = tsdb(
        [{"strPlayer": "Virgil van Dijk", "strTeam": "Liverpool", "strSubstitute": "No"},
         {"strPlayer": "Federico Chiesa", "strTeam": "Liverpool", "strSubstitute": "Yes"},
         {"strPlayer": "Sam Morsy", "strTeam": "Ipswich Town", "strSubstitute": "No"}],
        [{"strTimeline": "Goal", "strTimelineDetail": "Normal Goal", "strPlayer": "Alexander Isak", "strTeam": "Liverpool", "intTime": "6"},
         {"strTimeline": "Card", "strTimelineDetail": "Yellow Card", "strPlayer": "X", "strTeam": "Liverpool", "intTime": "30"},
         {"strTimeline": "Goal", "strTimelineDetail": "Own Goal", "strPlayer": "Sam Morsy", "strTeam": "Liverpool", "intTime": "70"}],
    )
    liv = r["equipos"]["Liverpool"]
    assert (liv["titulares"], liv["banca"], liv["jugadores"]) == (["Virgil van Dijk"], ["Federico Chiesa"], {})
    assert liv["filas"] == [{"nombre": "Virgil van Dijk", "titular": True}, {"nombre": "Federico Chiesa", "titular": False}]
    assert [g["jugador"] for g in r["goles"]] == ["Alexander Isak", "Sam Morsy"] and r["goles"][1]["tipo"] == "Own Goal"
    assert r["completo"] is False and r["publica_cambios"] is False and r["url"].endswith("/event/2494027")

    def suj(jugador, equipo):
        return {"jugador": jugador, "equipo": equipo, "rival": "x", "posicion": "M", "alcance": "partido", "ids": {}}

    isak = cruce.localizar_en_partido(r, suj("Alexander Isak", "Liverpool"), "tsdb", "Liverpool")
    assert isak["estado"] == "ok" and isak["rol"] is None  # fuera de la alineación recortada, pero con gol
    assert cruce.sugerir_gol("Alexander Isak", r, "Liverpool", isak)[0] == "YES"
    morsy = cruce.localizar_en_partido(r, suj("Sam Morsy", "Ipswich Town"), "tsdb", "Ipswich Town")
    assert morsy["estado"] == "ok" and cruce.sugerir_gol("Sam Morsy", r, "Ipswich Town", morsy)[0] == "NO"  # autogol no cuenta
    chiesa = cruce.localizar_en_partido(r, suj("Federico Chiesa", "Liverpool"), "tsdb", "Liverpool")
    assert cruce.sugerir_titular("Federico Chiesa", r, "Liverpool", chiesa)[0] == "NO"
    salah = cruce.localizar_en_partido(r, suj("Mohamed Salah", "Liverpool"), "tsdb", "Liverpool")
    assert salah["estado"] == "ausente"  # recortada: no confirma ausencias
    assert cruce.sugerir_titular("Mohamed Salah", r, "Liverpool", salah)[0] is None
    assert cruce.participo("Mohamed Salah", r, "Liverpool", salah) is None


def test_tsdb_nombre_exacto_unico_dentro_del_equipo():
    partido, espn, _ = resumenes_ucl()
    liga_pt = {"id": "lp-silva-titular", "subcategory": "Liga Portugal"}
    silva = {**SILVA_PORTO, "ids": {"espn": "9200"}}
    spec = {"tipo": "titular", "jugador": "Silva", "equipos": ["FC Porto", "Manchester City"]}
    dup = tsdb([{"strPlayer": "Silva", "strTeam": "FC Porto", "strSubstitute": "No"},
                {"strPlayer": "Silva", "strTeam": "FC Porto", "strSubstitute": "Yes"}])
    assert cruce.localizar_en_partido(dup, silva, "tsdb", "FC Porto")["estado"] == "ambiguo"
    e = cruce.resolver_accesorio(liga_pt, spec, "titular", partido, espn, dup, silva)
    assert e["escalar"] and "veredicto_sugerido" not in e and "nombre exacto" in e["razon"]

    unico = tsdb([{"strPlayer": "Silva", "strTeam": "FC Porto", "strSubstitute": "No"}])
    e = cruce.resolver_accesorio(liga_pt, spec, "titular", partido, espn, unico, silva)
    assert e["veredicto"] == "YES" and e["confianza"] == "alta" and e["sujeto_confirmado"]["tsdb"]["nombre"] == "Silva"

    rival = tsdb([{"strPlayer": "Silva", "strTeam": "Manchester City", "strSubstitute": "No"},
                  {"strPlayer": "Pepe", "strTeam": "FC Porto", "strSubstitute": "No"}])
    assert cruce.localizar_en_partido(rival, silva, "tsdb", "FC Porto")["estado"] == "otro_equipo"
    # un "Bernardo Silva" en el equipo no es "Silva": nunca subconjuntos en TheSportsDB
    parecido = tsdb([{"strPlayer": "Bernardo Silva", "strTeam": "FC Porto", "strSubstitute": "No"}])
    assert cruce.localizar_en_partido(parecido, silva, "tsdb", "FC Porto")["estado"] == "ausente"


def test_plan_futbol_exige_sujeto_y_escala_uefa_ambigua_o_temporada():
    base = {"question": "¿Bernardo Silva anota gol ante Porto en la Jornada 1 de la Champions?", "category": "Deportes",
            "subcategory": "Champions League", "market_type": "binary", "kind": "accesorio",
            "ends_at": "2026-09-16T19:00:00Z", "volume": 0, "num_trades": 0}
    mercados = [{**base, "id": "ucl-bernardo-gol", "sujeto": BERNARDO},
                {**base, "id": "ucl-bernardo-sin-sujeto"},
                {**base, "id": "ucl-bernardo-temporada", "sujeto": {**BERNARDO, "alcance": "temporada"}}]
    r = plan.armar_plan(mercados, http=http_futbol())
    res = {e["id"]: e for e in r["resoluciones"]}
    esc = {e["id"]: e for e in r["escalados"]}
    assert res["ucl-bernardo-gol"]["veredicto"] == "NO" and res["ucl-bernardo-gol"]["confianza"] == "alta"
    assert errores_identidad(mercados[0], res["ucl-bernardo-gol"]) == []
    assert "sin sujeto" in esc["ucl-bernardo-sin-sujeto"]["razon"] and "veredicto_sugerido" not in esc["ucl-bernardo-sin-sujeto"]
    assert "alcance 'temporada'" in esc["ucl-bernardo-temporada"]["razon"]

    # la UEFA lista dos partidos equivalentes: sin segunda fuente (ni TheSportsDB) y sin sugerencia
    lista = fixture_json("futbol_silva_min.json")["uefa_partidos"]
    http = http_futbol(uefa_partidos=lista + [{**lista[0], "id": "2049601"}])
    r = plan.armar_plan(mercados[:1], http=http)
    assert r["resoluciones"] == [] and not [u for u in http.urls if "thesportsdb" in u]
    e = r["escalados"][0]
    assert e["id"] == "ucl-bernardo-gol" and "veredicto_sugerido" not in e and "ambiguo" in e["razon"]
