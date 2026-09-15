"""Identidad del sujeto de un accesorio de jugador: forma (resolucion/sujeto.py) y
búsqueda de ids por fuente (resolucion/identidad.py). Sin red: FakeHttp con
planteles recortados (tests/fixtures)."""
from datetime import datetime, timezone

import pytest

from app.services.resolucion import identidad
from app.services.resolucion.sujeto import (IDS_REQUERIDOS, errores_identidad, normalizar_sujeto, requiere_sujeto,
                                            spec_de_pregunta, validar_sujeto)
from tests.fakes import FakeHttp, fixture_json, fixture_texto

PREGUNTA_ALLEN = "¿Josh Allen lanzará 2 o más pases de touchdown en la Semana 1?"
SUJETO_ALLEN = {"jugador": "Josh Allen", "equipo": "Bills", "rival": "Texans", "posicion": "QB", "alcance": "partido",
                "ids": {"espn": "3918298", "cbs": "2181054"}}
PREGUNTA_CHERKI = "¿Rayan Cherki será titular con Manchester City ante Porto en la Jornada 1 de la Champions?"
SUJETO_CHERKI = {"jugador": "Rayan Cherki", "equipo": "Manchester City", "rival": "FC Porto", "posicion": "M",
                 "alcance": "partido", "ids": {"espn": "5001", "uefa": "250500"}}


def spec_allen():
    return requiere_sujeto("DEPORTES", "binario", "NFL", PREGUNTA_ALLEN)


# ── requiere_sujeto / spec_de_pregunta ───────────────────────────────────────

def test_requiere_sujeto_fail_closed_por_liga_y_parser():
    esperado = {"jugador": "Josh Allen", "tipo": "pases_td", "umbral": 2.0}
    for category in ("DEPORTES", "Deportes", None):       # nombre o value del enum; no excluye nada
        for tipo in ("binario", "binary", None):
            assert requiere_sujeto(category, tipo, "NFL", PREGUNTA_ALLEN) == esperado
    assert requiere_sujeto("DEPORTES", "multi", "NFL", PREGUNTA_ALLEN) is None   # los multi no llevan sujeto
    assert requiere_sujeto("DEPORTES", "binario", "F1", PREGUNTA_ALLEN) is None  # liga sin fuente automática
    assert requiere_sujeto("DEPORTES", "binario", None, PREGUNTA_ALLEN) is None
    # accesorios de equipo o de evento no parsean como jugador
    assert requiere_sujeto("DEPORTES", "binario", "NFL", "¿Los Bills anotarán 30 o más puntos contra los Texans en la Semana 1?") is None
    assert requiere_sujeto("DEPORTES", "binario", "LaLiga", "¿Habrá más de 2.5 goles en Real Madrid vs Barcelona?") is None
    # el parser es el de la liga: una pregunta de fútbol en NFL no exige sujeto (y viceversa)
    assert requiere_sujeto("DEPORTES", "binario", "NFL", PREGUNTA_CHERKI) is None
    assert requiere_sujeto("DEPORTES", "binario", "Premier League", PREGUNTA_ALLEN) is None


def test_spec_de_pregunta_fija_orientacion_solo_si_la_pregunta_la_da():
    assert spec_de_pregunta(PREGUNTA_CHERKI, "Champions League") == {
        "tipo": "titular", "jugador": "Rayan Cherki", "equipos": ["Manchester City", "Porto"],
        "club": "Manchester City", "rival": "Porto"}
    en = spec_de_pregunta("¿Mateo Kovačić será titular en Crystal Palace vs Manchester City?", "Premier League")
    assert en["tipo"] == "titular" and "club" not in en and "rival" not in en
    gol = spec_de_pregunta("¿Erling Haaland anota gol ante Porto en la Jornada 1 de la Champions?", "Champions League")
    assert (gol["tipo"], gol["jugador"], gol["rival"]) == ("gol", "Erling Haaland", "Porto")


def test_ids_requeridos_por_liga():
    assert IDS_REQUERIDOS("NFL") == {"espn", "cbs"}
    assert IDS_REQUERIDOS("Champions League") == {"espn", "uefa"}
    assert IDS_REQUERIDOS("LaLiga") == {"espn"}
    assert IDS_REQUERIDOS(None) == set()


# ── validar_sujeto ───────────────────────────────────────────────────────────

def test_validar_sujeto_valido_y_normalizado():
    assert validar_sujeto(spec_allen(), SUJETO_ALLEN, "NFL") == []
    crudo = {**SUJETO_ALLEN, "posicion": " qb ", "ids": {"espn": 3918298, "cbs": "2181054 ", "tsdb": None}}
    assert validar_sujeto(spec_allen(), crudo, "NFL") == []
    assert normalizar_sujeto(crudo) == {**SUJETO_ALLEN, "ids": {"espn": "3918298", "cbs": "2181054"}}
    # temporada: el rival puede quedar vacío
    temporada = {**SUJETO_ALLEN, "alcance": "temporada", "rival": ""}
    assert validar_sujeto(requiere_sujeto(None, None, "NFL", "¿Josh Allen anotará al menos 10 touchdowns en la temporada?"),
                          temporada, "NFL") == []


@pytest.mark.parametrize("cambio,fragmento", [
    ({"jugador": "Josh Hines-Allen"}, "debe ser idéntico"),
    ({"jugador": "Allen"}, "debe ser idéntico"),
    ({"ids": {"espn": "3918298"}}, "falta ids.cbs"),
    ({"ids": {"espn": "abc", "cbs": "2181054"}}, "no es un id numérico"),
    ({"ids": {"espn": "3918298", "cbs": "2181054", "nfl": "1"}}, "fuentes desconocidas en ids: nfl"),
    ({"posicion": "DE"}, "exige posicion QB"),
    ({"alcance": "semana"}, "alcance 'semana' inválido"),
    ({"rival": "Buffalo Bills"}, "parecen el mismo club"),
    ({"rival": ""}, "'rival' vacío"),
    ({"apodo": "El Rey"}, "claves desconocidas en sujeto: apodo"),
], ids=["homonimo", "solo-apellido", "sin-cbs", "id-no-numerico", "fuente-desconocida", "pases-de-un-DE",
        "alcance-invalido", "equipo-igual-rival", "sin-rival", "clave-extra"])
def test_validar_sujeto_errores_nfl(cambio, fragmento):
    errs = validar_sujeto(spec_allen(), {**SUJETO_ALLEN, **cambio}, "NFL")
    assert any(fragmento in e for e in errs), errs


def test_validar_sujeto_forma_minima():
    sin_alcance = {k: v for k, v in SUJETO_ALLEN.items() if k != "alcance"}
    assert any("faltan claves en sujeto: alcance" in e for e in validar_sujeto(spec_allen(), sin_alcance, "NFL"))
    assert "no es un accesorio de jugador" in validar_sujeto(None, SUJETO_ALLEN, "NFL")[0]
    assert "debe ser un mapa" in validar_sujeto(spec_allen(), "Josh Allen", "NFL")[0]


def test_validar_sujeto_futbol_equipos_de_la_pregunta_y_uefa():
    spec = spec_de_pregunta(PREGUNTA_CHERKI, "Champions League")
    assert validar_sujeto(spec, SUJETO_CHERKI, "Champions League") == []
    errs = validar_sujeto(spec, {**SUJETO_CHERKI, "ids": {"espn": "5001"}}, "Champions League")
    assert any("falta ids.uefa" in e for e in errs)
    # la pregunta dice "con Manchester City": equipo y rival invertidos no pasan
    errs = validar_sujeto(spec, {**SUJETO_CHERKI, "equipo": "FC Porto", "rival": "Manchester City"}, "Champions League")
    assert any("juega con 'Manchester City'" in e for e in errs)
    errs = validar_sujeto(spec, {**SUJETO_CHERKI, "rival": "Benfica"}, "Champions League")
    assert any("'Porto' (de la pregunta) no es ni sujeto.equipo ni sujeto.rival" in e for e in errs)
    # fuera de la UEFA basta ESPN
    liga = spec_de_pregunta("¿Kylian Mbappé será titular en Real Madrid vs Barcelona?", "LaLiga")
    mbappe = {"jugador": "Kylian Mbappé", "equipo": "Real Madrid", "rival": "Barcelona", "posicion": "F",
              "alcance": "partido", "ids": {"espn": "231388"}}
    assert validar_sujeto(liga, mbappe, "LaLiga") == []
    assert any("no son {equipo, rival}" in e or "no es ni" in e
               for e in validar_sujeto(liga, {**mbappe, "rival": "Sevilla"}, "LaLiga"))


# ── errores_identidad (lo que validar_entrada no cubre en test_agent_resolver) ─

def _detalle(question, liga, sujeto):
    return {"category": "Deportes", "market_type": "binary", "subcategory": liga, "question": question, "sujeto": sujeto}


def test_errores_identidad_thesportsdb_uefa_y_equipo_cruzado():
    mbappe = {"jugador": "Kylian Mbappé", "equipo": "Real Madrid", "rival": "Barcelona", "posicion": "F",
              "alcance": "partido", "ids": {"espn": "231388"}}
    detalle = _detalle("¿Kylian Mbappé será titular en Real Madrid vs Barcelona?", "LaLiga", mbappe)
    entrada = {"veredicto": "YES", "fuente_1": "https://www.espn.com/soccer/lineups/_/gameId/1",
               "fuente_2": "https://www.thesportsdb.com/event/2",
               "sujeto_confirmado": {"jugador": "Kylian Mbappé", "equipo": "Real Madrid",
                                     "espn": {"id": "231388", "nombre": "Kylian Mbappé", "equipo": "Real Madrid"},
                                     "tsdb": {"nombre": "Kylian Mbappe", "equipo": "Real Madrid"}}}
    assert errores_identidad(detalle, entrada) == []
    sc = entrada["sujeto_confirmado"]
    mal_tsdb = {**entrada, "sujeto_confirmado": {**sc, "tsdb": {"nombre": "Mbappé", "equipo": "Real Madrid"}}}
    assert any("tsdb.nombre" in e for e in errores_identidad(detalle, mal_tsdb))
    cruzado = {**entrada, "sujeto_confirmado": {**sc, "equipo": "Barcelona"}}
    assert any("sujeto_confirmado.equipo 'Barcelona'" in e for e in errores_identidad(detalle, cruzado))
    # el mercado con un sujeto inválido tampoco se resuelve
    assert any("sujeto del mercado inválido" in e
               for e in errores_identidad({**detalle, "sujeto": {**mbappe, "ids": {}}}, entrada))
    # un mercado que no es de jugador no exige nada
    assert errores_identidad(_detalle("¿Quién gana Real Madrid vs Barcelona?", "LaLiga", None), {}) == []

    ucl = _detalle(PREGUNTA_CHERKI, "Champions League", SUJETO_CHERKI)
    entrada_ucl = {"veredicto": "YES", "fuente_1": "https://www.espn.com/soccer/lineups/_/gameId/1",
                   "fuente_2": "https://www.uefa.com/uefachampionsleague/match/2049600/",
                   "sujeto_confirmado": {"jugador": "Rayan Cherki", "equipo": "Manchester City",
                                         "espn": {"id": "5001", "nombre": "Rayan Cherki", "equipo": "Manchester City"},
                                         "uefa": {"id": "250501", "nombre": "Rayan Cherki", "equipo": "Manchester City"}}}
    assert any("uefa.id '250501'" in e for e in errores_identidad(ucl, entrada_ucl))


# ── identidad: candidatos exactos, planteles y chequeo cruzado ───────────────

def test_candidato_unico_nunca_fuzzy():
    roster = fixture_json("espn_roster_buf_min.json")
    plantel = identidad.plantel_espn(FakeHttp({"football/nfl/teams/buf/roster": roster["roster"]}), "NFL",
                                     {"id": "2", "abbr": "BUF"})
    assert {p["id"] for p in plantel} == {"3918298", "3115293", "4259166", "3917232"}  # todos los grupos
    j, nota = identidad.candidato_unico(plantel, "Josh Allen")
    assert j["id"] == "3918298" and j["posicion"] == "QB" and nota == ""
    assert identidad.candidato_unico(plantel, "Kyle Allen")[0]["id"] == "3115293"
    # solo el apellido: dos parecidos, ninguno elegido
    j, nota = identidad.candidato_unico(plantel, "Allen")
    assert j is None and "3918298" in nota and "3115293" in nota and "no se elige ninguno" in nota
    # el homónimo de otro equipo nunca es "el más cercano"
    hines = [{"id": "3915239", "nombre": "Josh Hines-Allen", "nombres": ["Josh Hines-Allen"], "posicion": "DE", "jersey": "41"}]
    j, nota = identidad.candidato_unico(hines, "Josh Allen")
    assert j is None and "no está en el plantel" in nota
    assert identidad.candidato_unico(plantel, "Jos Allen")[0] is None  # errata: tampoco
    duplicado = plantel + [{"id": "999", "nombre": "Josh Allen", "nombres": ["Josh Allen"]}]
    j, nota = identidad.candidato_unico(duplicado, "Josh Allen")
    assert j is None and "2 jugadores con el nombre exacto" in nota
    # sufijos generacionales y apóstrofes del slug de CBS
    assert identidad.clave_nombre("Marvin Harrison Jr.") == identidad.clave_nombre("Marvin Harrison")
    swift = [{"id": "2", "nombre": "Dandre Swift", "nombres": ["dandre-swift"]}]
    assert identidad.candidato_unico(swift, "D'Andre Swift", "cbs")[0]["id"] == "2"


def test_roster_e_indice_de_cbs():
    html = fixture_texto("cbs_roster_buf_min.html")
    roster = {p["id"]: p for p in identidad.parsear_roster_cbs(html)}
    assert set(roster) == {"2181054", "1000009", "1000008", "1000017"}  # el enlace doble se deduplica
    assert {k: roster["2181054"][k] for k in ("slug", "jersey", "posicion")} == {"slug": "josh-allen", "jersey": "17", "posicion": "QB"}
    indice = FakeHttp(text_map={"cbssports.com/nfl/teams/": '<a href="/nfl/teams/BUF/stats/">s</a>'
                                                            '<a href="/nfl/teams/BUF/buffalo-bills/">b</a>'})
    assert identidad.slugs_cbs(indice) == {"BUF": "buffalo-bills"}


def test_cruzar_dorsal_y_posicion():
    espn = {"id": "3918298", "nombre": "Josh Allen", "jersey": "17", "posicion": "QB"}
    assert identidad.cruzar(espn, {"id": "2181054", "nombre": "Josh Allen", "jersey": "#17", "posicion": "QB"}, "CBS", True) == ([], [])
    errs, _ = identidad.cruzar(espn, {"id": "1", "nombre": "Josh Allen", "jersey": "71", "posicion": "QB"}, "CBS", True)
    assert any("dorsal distinto" in e for e in errs)
    errs, _ = identidad.cruzar(espn, {"id": "1", "nombre": "Josh Allen", "jersey": "17", "posicion": "WR"}, "CBS", True)
    assert any("posición distinta" in e for e in errs)
    errs, avisos = identidad.cruzar(espn, {"id": "1", "nombre": "Josh Allen", "jersey": "", "posicion": ""}, "CBS", True)
    assert errs == [] and len(avisos) == 2  # faltantes: aviso, no error
    assert identidad.cruzar({**espn, "posicion": "PK"}, {"id": "1", "jersey": "17", "posicion": "K"}, "CBS", True)[0] == []
    assert identidad.cruzar(espn, {"id": "1", "jersey": "17", "posicion": "WR"}, "UEFA", False)[0] == []  # fútbol: solo dorsal


def http_rosters(cbs_roster: str | None = None, con_cbs: bool = True) -> FakeHttp:
    roster = fixture_json("espn_roster_buf_min.json")
    html = fixture_texto("cbs_roster_buf_min.html")
    textos = {"/nfl/teams/BUF/buffalo-bills/roster/": cbs_roster or html, "cbssports.com/nfl/teams/": html} if con_cbs else {}
    return FakeHttp({"football/nfl/teams/buf/roster": roster["roster"], "football/nfl/teams": roster["teams"]}, textos)


def test_buscar_ids_nfl():
    base = {"jugador": "Josh Allen", "equipo": "Bills", "rival": "Texans", "alcance": "partido"}
    sujeto, errores, avisos = identidad.buscar_ids(http_rosters(), "NFL", base)
    assert errores == [] and avisos == [] and sujeto == SUJETO_ALLEN
    assert validar_sujeto(spec_allen(), sujeto, "NFL") == []
    # un id ya escrito que no coincide no se pisa
    _, errores, _ = identidad.buscar_ids(http_rosters(), "NFL", {**base, "ids": {"espn": "3915239"}})
    assert any("ids.espn ya dice 3915239" in e for e in errores)
    # dorsal distinto entre ESPN y CBS: ¿otra persona?
    otro = fixture_texto("cbs_roster_buf_min.html").replace('TableBase-bodyTd">17</td>', 'TableBase-bodyTd">71</td>')
    _, errores, _ = identidad.buscar_ids(http_rosters(cbs_roster=otro), "NFL", base)
    assert any("dorsal distinto" in e for e in errores)
    _, errores, _ = identidad.buscar_ids(http_rosters(), "NFL", {**base, "posicion": "WR"})
    assert any("sujeto.posicion 'WR'" in e for e in errores)
    _, errores, _ = identidad.buscar_ids(http_rosters(con_cbs=False), "NFL", base)
    assert any("CBS no respondió" in e for e in errores)
    _, errores, _ = identidad.buscar_ids(http_rosters(), "NFL", {**base, "equipo": "Bengals"})
    assert errores and errores[0].startswith("ESPN:")
    _, errores, _ = identidad.buscar_ids(http_rosters(), "NFL", {**base, "jugador": "Josh Hines-Allen"})
    assert any("no está en el plantel" in e for e in errores)


def http_uefa(ranking: list, partidos: list | None = None) -> FakeHttp:
    fut = fixture_json("futbol_silva_min.json")
    return FakeHttp({
        "soccer/uefa.champions/teams/382/roster": {"athletes": [
            {"id": "9100", "displayName": "Bernardo Silva", "fullName": "Bernardo Mota Veiga de Carvalho e Silva",
             "jersey": "20", "position": {"abbreviation": "M"}}]},
        "soccer/uefa.champions/teams": {"sports": [{"leagues": [{"teams": [
            {"team": {"id": "382", "abbreviation": "MNC", "displayName": "Manchester City", "shortDisplayName": "Man City"}},
            {"team": {"id": "437", "abbreviation": "POR", "displayName": "FC Porto", "shortDisplayName": "Porto"}}]}]}]},
        "comp.uefa.com/v2/teams": [
            {"id": 52919, "internationalName": "Man City", "translations": {"displayOfficialName": {"EN": "Manchester City"}}},
            {"id": "50064", "internationalName": "Porto", "translations": {"displayOfficialName": {"EN": "FC Porto"}}}],
        "compstats.uefa.com/v1/player-ranking": ranking,
        "/lineups": fut["uefa_lineups"],
        "match.uefa.com/v5/matches?": partidos or [],
    })


def test_buscar_ids_uefa_team_id_de_la_fila_y_respaldo_por_alineaciones():
    base = {"jugador": "Bernardo Silva", "equipo": "Manchester City", "rival": "FC Porto", "alcance": "partido"}
    fecha = datetime(2026, 9, 16, 19, 0, tzinfo=timezone.utc)

    def fila(team_id, pid, dorsal):
        return {"teamId": team_id, "player": {"id": pid, "internationalName": "Bernardo Silva", "clubJerseyNumber": dorsal,
                                              "fieldPosition": "MIDFIELDER", "clubId": "52919"}}

    # la segunda fila es de otro equipo aunque player.clubId diga City: se ignora
    http = http_uefa([fila("52919", 250000, 20), fila("50064", 250099, 8)])
    sujeto, errores, avisos = identidad.buscar_ids(http, "Champions League", base, fecha)
    assert errores == [] and sujeto["ids"] == {"espn": "9100", "uefa": "250000"} and sujeto["posicion"] == "M"
    assert any("seasonYear=2027" in u and "teamId=52919" in u for u in http.urls)

    # compstats no lo trae (sin minutos): respaldo con las alineaciones de un partido previo del club
    previo = [{"id": "2049600", "homeTeam": {"id": 52919}, "awayTeam": {"id": "50064"}}]
    sujeto, errores, avisos = identidad.buscar_ids(http_uefa([], previo), "Champions League", base, fecha)
    assert errores == [] and sujeto["ids"]["uefa"] == "250000"
    assert any("no aparece en compstats" in a for a in avisos)

    # dorsal distinto ESPN ↔ UEFA: error
    _, errores, _ = identidad.buscar_ids(http_uefa([fila("52919", 250000, 10)]), "Champions League", base, fecha)
    assert any("dorsal distinto" in e for e in errores)


# ── hallazgos de revisión ────────────────────────────────────────────────────

def test_spec_de_pregunta_sujeto_que_no_es_jugador():
    """Accesorios de evento o de equipo con verbo en singular: el parser de gol
    tomaba "Se" / "El América" como jugador y exigía sujeto."""
    evento = "¿Se anotará un gol antes del minuto 10 en América vs Chivas?"
    for q in (evento, "¿El América marcará gol en la jornada 3 contra Chivas?",
              "¿Alguien anotará gol ante Chivas?", "¿Quién marcará el primer gol ante Chivas?",
              "¿Ningún jugador del América anotará gol ante Chivas?"):
        assert spec_de_pregunta(q, "Liga MX") is None, q
        assert requiere_sujeto("DEPORTES", "binario", "Liga MX", q) is None, q
    # el sujeto es uno de los equipos de la pregunta
    assert spec_de_pregunta("¿Club América será titular en América vs Chivas?", "Liga MX") is None
    # jugadores de un solo token o con partícula siguen exigiendo sujeto
    assert spec_de_pregunta("¿Mbappé marcará al menos un gol en su primer partido de la Champions?", "Champions League")["jugador"] == "Mbappé"
    assert spec_de_pregunta("¿Lo Celso anota gol ante Betis?", "LaLiga")["jugador"] == "Lo Celso"
    assert spec_de_pregunta("¿De Bruyne será titular en Napoli vs Inter?", "Serie A")["jugador"] == "De Bruyne"
    # sin sujeto: validar_entrada no lo trata como accesorio de jugador
    assert errores_identidad(_detalle(evento, "Liga MX", None), {"veredicto": "YES"}) == []
    assert "no es un accesorio de jugador" in validar_sujeto(spec_de_pregunta(evento, "Liga MX"),
                                                            {**SUJETO_ALLEN, "jugador": "Se"}, "Liga MX")[0]


def test_errores_identidad_exige_los_ids_obligatorios_de_la_liga():
    mbappe = {"jugador": "Kylian Mbappé", "equipo": "Real Madrid", "rival": "Barcelona", "posicion": "F",
              "alcance": "partido", "ids": {"espn": "231388"}}
    laliga = _detalle("¿Kylian Mbappé será titular en Real Madrid vs Barcelona?", "LaLiga", mbappe)
    espn = {"id": "231388", "nombre": "Kylian Mbappé", "equipo": "Real Madrid"}
    manual = {"equipo": "Real Madrid", "nota": "acta oficial"}
    base = {"veredicto": "YES", "fuente_1": "https://www.espn.com/soccer/lineups/_/gameId/1",
            "fuente_2": "https://www.laliga.com/partido/x",
            "sujeto_confirmado": {"jugador": "Kylian Mbappé", "equipo": "Real Madrid", "espn": espn, "manual": manual}}
    assert errores_identidad(laliga, base) == []  # fuera de la UEFA: ESPN + manual
    sin_espn = {**base, "fuente_1": "https://www.thesportsdb.com/event/2",
                "sujeto_confirmado": {**base["sujeto_confirmado"], "tsdb": {"nombre": "Kylian Mbappé", "equipo": "Real Madrid"}}}
    assert any("por id en espn" in e for e in errores_identidad(laliga, sin_espn))

    ucl = _detalle(PREGUNTA_CHERKI, "Champions League", SUJETO_CHERKI)
    sc = {"jugador": "Rayan Cherki", "equipo": "Manchester City",
          "espn": {"id": "5001", "nombre": "Rayan Cherki", "equipo": "Manchester City"},
          "tsdb": {"nombre": "Rayan Cherki", "equipo": "Manchester City"}}
    con_tsdb = {"veredicto": "NO", "fuente_1": "https://www.espn.com/soccer/lineups/_/gameId/1",
                "fuente_2": "https://www.thesportsdb.com/event/2", "sujeto_confirmado": sc}
    assert any("por id en uefa" in e for e in errores_identidad(ucl, con_tsdb))
    assert errores_identidad(ucl, {**con_tsdb, "veredicto": "CANCELAR"}) == []  # CANCELAR: basta el equipo


def test_cruzar_posicion_por_grupo_nfl():
    def cruce_pos(pe, po):
        return identidad.cruzar({"id": "1", "nombre": "X", "jersey": "20", "posicion": pe},
                                {"id": "2", "nombre": "X", "jersey": "20", "posicion": po}, "CBS", True)

    for pe, po in (("S", "SAF"), ("S", "DB"), ("CB", "DB"), ("LB", "OLB"), ("DT", "DE"), ("DT", "NT"), ("FB", "RB")):
        errs, avisos = cruce_pos(pe, po)
        assert errs == [] and any("mismo grupo" in a for a in avisos), (pe, po)
    for pe, po in (("QB", "RB"), ("TE", "WR"), ("WR", "CB"), ("RB", "LB")):
        assert any("posición distinta" in e for e in cruce_pos(pe, po)[0]), (pe, po)


def test_uefa_alineaciones_desc_y_paginado():
    fecha = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)

    def partido(pid, local, visita, dia):
        return {"id": pid, "homeTeam": {"id": local}, "awayTeam": {"id": visita},
                "kickOffTime": {"dateTime": f"2026-03-{dia:02d}T20:00:00Z"}}

    def lineup(pid):
        return {"homeTeam": {"team": {"id": 52919}, "field": [{"player": {"id": pid, "internationalName": f"J{pid}"}}]},
                "awayTeam": {"team": {"id": 1}, "field": []}}

    # página 1: un partido posterior a `hasta` (mismo día) y uno propio; relleno ajeno hasta 100 filas
    p1 = [partido("m-futuro", 52919, 1, 15), partido("m1", 52919, 1, 11)] + [partido(f"x{i}", 7, 8, 10) for i in range(98)]
    p2 = [partido("m2", 52919, 1, 5), partido("m3", 52919, 1, 1), partido("m4", 52919, 1, 1)]
    http = FakeHttp({"/matches/m1/lineups": lineup(101), "/matches/m2/lineups": lineup(102),
                     "/matches/m3/lineups": lineup(103), "/matches/m4/lineups": lineup(104),
                     "/matches/m-futuro/lineups": lineup(999),
                     "offset=0&order=DESC": p1, "offset=100&order=DESC": p2})
    plantel = identidad.plantel_uefa_alineaciones(http, "Champions League", "52919", 2026, fecha, max_partidos=3)
    assert [p["id"] for p in plantel] == ["101", "102", "103"]  # los 3 más recientes antes de `hasta`, en dos páginas
    assert not [u for u in http.urls if "order=ASC" in u] and not [u for u in http.urls if "m-futuro" in u]
