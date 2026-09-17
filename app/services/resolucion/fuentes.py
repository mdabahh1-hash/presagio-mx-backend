"""Clientes de solo lectura de resultados de fútbol (stdlib, sin API key).

ESPN  — site.api.espn.com: scoreboard por liga y rango de fechas (jornada
        completa, marcador, estado) y summary por evento (alineaciones con
        titulares y goles, con ids de equipo y de jugador). Bloquea User-Agents
        de navegador y de Python; acepta el de curl.
TSDB  — thesportsdb.com API v1 con la key pública `3`. La capa gratuita recorta
        los listados (eventsday devuelve 3 filas), así que solo se usa la
        búsqueda por partido (`searchevents.php?e=Local_vs_Visitante`), que sí
        devuelve el marcador final. Sirve como segunda fuente independiente.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "curl/8.1.2"}
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports"
TSDB_API = "https://www.thesportsdb.com/api/v1/json/3"

# subcategoría de Veredikt → (ruta ESPN "deporte/liga", id de liga TSDB, nombre
# de liga TSDB tal como aparece en strFilename). Extender aquí al sembrar una
# liga nueva; una subcategoría ausente se escala como "sin fuente".
LIGAS: dict[str, tuple[str, str, str]] = {
    "Serie A": ("soccer/ita.1", "4332", "Italian Serie A"),
    "LaLiga": ("soccer/esp.1", "4335", "Spanish La Liga"),
    "Premier League": ("soccer/eng.1", "4328", "English Premier League"),
    "Bundesliga": ("soccer/ger.1", "4331", "German Bundesliga"),
    "Ligue 1": ("soccer/fra.1", "4334", "French Ligue 1"),
    "Liga Portugal": ("soccer/por.1", "4344", "Portuguese Primeira Liga"),
    "MLS": ("soccer/usa.1", "4346", "American Major League Soccer"),
    "Liga MX": ("soccer/mex.1", "4350", "Mexican Liga MX"),
    "Saudi Pro League": ("soccer/ksa.1", "4668", "Saudi-Arabian Pro League"),
    "Champions League": ("soccer/uefa.champions", "4480", "UEFA Champions League"),
    "NFL": ("football/nfl", "4391", "NFL"),
}


def deporte(liga: str) -> str:
    """'futbol' | 'nfl' según la ruta ESPN de la liga."""
    code = LIGAS.get(liga, ("soccer/",))[0]
    return "nfl" if code.startswith("football/nfl") else "futbol"


def _url_partido(liga: str, event_id: str) -> str:
    return (f"https://www.espn.com/nfl/game/_/gameId/{event_id}" if deporte(liga) == "nfl"
            else f"https://www.espn.com/soccer/match/_/gameId/{event_id}")

# Nombre en ESPN (o en el mercado) → nombre exacto en TheSportsDB, para los
# clubes que las transformaciones genéricas no resuelven. Se prueba primero.
TSDB_ALIAS: dict[str, str] = {
    "Red Bull New York": "New York Red Bulls",
    "LAFC": "Los Angeles FC",
    "Athletic Club": "Athletic Bilbao",
    "FC Cologne": "Köln",
    "Colonia": "Köln",
    "Alavés": "Deportivo Alavés",
    "Guadalajara": "CD Guadalajara",
    "Neom SC": "Neom",
    "Internazionale": "Inter Milan",
    "Inter": "Inter Milan",
    "Deportivo": "Deportivo de A Coruña",
    "Nacional": "Nacional de Madeira",
    "Brighton & Hove Albion": "Brighton and Hove Albion",
    "AFC Bournemouth": "Bournemouth",
    "Wolverhampton Wanderers": "Wolves",
    "Tottenham Hotspur": "Tottenham",
    "1. FC Union Berlin": "Union Berlin",
    "Paris Saint-Germain": "Paris SG",
    "Atlético de San Luis": "Atletico de San Luis",
    "Sporting CP": "Sporting CP",
}

_LEGAL = ("FC", "CF", "SC", "AFC", "CD", "AC", "SS", "SSC", "US", "AS", "TSG", "VfB", "VfL", "SV",
          "BSC", "1.", "07", "04", "05", "09", "1899", "1846")


def variantes_nombre(*nombres: str) -> list[str]:
    """Variantes de nombre para buscar en TheSportsDB, en orden de probabilidad:
    alias explícito, nombre tal cual, & → and, sin siglas legales (FC Porto →
    Porto, Inter Miami CF → Inter Miami), Al X → Al-X."""
    out: list[str] = []

    def add(n: str) -> None:
        n = " ".join(n.split())
        if n and n not in out:
            out.append(n)

    for n in nombres:
        if not n:
            continue
        if n in TSDB_ALIAS:
            add(TSDB_ALIAS[n])
        add(n)
        add(n.replace("&", "and"))
        add(n.replace(".", ""))  # D.C. United → DC United
        toks = n.replace("&", "and").replace(".", "").split()
        while toks and toks[0] in _LEGAL:
            toks = toks[1:]
        while toks and toks[-1] in _LEGAL:
            toks = toks[:-1]
        if len(toks) >= 1:
            add(" ".join(toks))
        if n.startswith("Al ") or n.startswith("Al-"):
            add("Al-" + n[3:])
            add("Al " + n[3:])
    return out

# Estados normalizados de un partido.
FT, AET, POSTPONED, CANCELLED, SCHEDULED, LIVE, UNKNOWN = (
    "FT", "AET", "POSTPONED", "CANCELLED", "SCHEDULED", "LIVE", "UNKNOWN",
)

_ESPN_ESTADOS = {
    "STATUS_FULL_TIME": FT,
    "STATUS_FINAL": FT,
    "STATUS_FINAL_AET": AET,
    "STATUS_FINAL_PEN": AET,
    "STATUS_POSTPONED": POSTPONED,
    "STATUS_CANCELED": CANCELLED,
    "STATUS_ABANDONED": CANCELLED,
    "STATUS_SCHEDULED": SCHEDULED,
    "STATUS_DELAYED": SCHEDULED,
    "STATUS_IN_PROGRESS": LIVE,
    "STATUS_HALFTIME": LIVE,
    "STATUS_FIRST_HALF": LIVE,
    "STATUS_SECOND_HALF": LIVE,
    "STATUS_END_PERIOD": LIVE,      # NFL: fin de cuarto
    "STATUS_SUSPENDED": POSTPONED,
}
_TSDB_ESTADOS = {
    "FT": FT, "Match Finished": FT, "AET": AET, "PEN": AET,
    "PST": POSTPONED, "Postponed": POSTPONED, "CANC": CANCELLED, "Cancelled": CANCELLED,
    "ABD": CANCELLED, "NS": SCHEDULED, "Not Started": SCHEDULED, "TBD": SCHEDULED,
}


@dataclass
class Partido:
    fuente: str            # "espn" | "tsdb"
    id: str
    url: str               # página humana para la bitácora
    kickoff: datetime      # UTC
    home: str
    away: str
    home_score: int | None
    away_score: int | None
    estado: str            # FT, AET, POSTPONED, ...
    alias: list[str] = field(default_factory=list)  # nombres alternos [home..., away...]
    liga: str = ""

    @property
    def marcador(self) -> str:
        if self.home_score is None or self.away_score is None:
            return "sin marcador"
        return f"{self.home} {self.home_score}-{self.away_score} {self.away}"


class Http:
    """GET JSON con reintentos y throttle por host (TSDB gratis ≈ 30 req/min)."""

    def __init__(self, pausa_tsdb: float = 2.0):
        self.pausa_tsdb = pausa_tsdb  # TSDB gratis ≈ 30 req/min; 429 si se pasa
        self._ultimo_tsdb = 0.0
        self.cache: dict[str, dict] = {}
        self.consultas = 0

    def get(self, url: str) -> dict:
        if url in self.cache:
            return self.cache[url]
        es_tsdb = "thesportsdb" in url
        ultimo_error: Exception | None = None
        for intento in range(4):
            if es_tsdb:
                espera = self.pausa_tsdb - (time.monotonic() - self._ultimo_tsdb)
                if espera > 0:
                    time.sleep(espera)
                self._ultimo_tsdb = time.monotonic()
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.load(r)
                self.consultas += 1
                self.cache[url] = data
                return data
            except urllib.error.HTTPError as e:
                ultimo_error = e
                if e.code == 429:
                    time.sleep(30 * (intento + 1))  # límite de tasa: esperar y reintentar
                    continue
                if 500 <= e.code < 600:
                    time.sleep(2 * (intento + 1))
                    continue
                break  # 4xx distinto de 429: no insistir
            except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
                ultimo_error = e
                time.sleep(2 * (intento + 1))
        raise RuntimeError(f"GET {url} falló: {ultimo_error}")

    def get_text(self, url: str) -> str:
        """GET de una página HTML (CBS): mismos reintentos, sin throttle."""
        if url in self.cache:
            return self.cache[url]
        ultimo_error: Exception | None = None
        for intento in range(3):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=30) as r:
                    texto = r.read().decode("utf-8", errors="replace")
                self.consultas += 1
                self.cache[url] = texto
                return texto
            except urllib.error.HTTPError as e:
                ultimo_error = e
                if e.code == 429 or 500 <= e.code < 600:
                    time.sleep(5 * (intento + 1))
                    continue
                break
            except (urllib.error.URLError, TimeoutError) as e:
                ultimo_error = e
                time.sleep(2 * (intento + 1))
        raise RuntimeError(f"GET {url} falló: {ultimo_error}")


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)


# ── ESPN ─────────────────────────────────────────────────────────────────────

def _espn_partido(e: dict, liga: str) -> Partido:
    c = e["competitions"][0]
    por_lado = {x["homeAway"]: x for x in c["competitors"]}
    h, a = por_lado["home"], por_lado["away"]
    tipo = e["status"]["type"]
    estado = _ESPN_ESTADOS.get(tipo.get("name"), FT if tipo.get("completed") else UNKNOWN)

    def score(x: dict) -> int | None:
        s = x.get("score")
        try:
            return int(float(s)) if s not in (None, "") else None
        except ValueError:
            return None

    def nombres(x: dict) -> list[str]:
        t = x["team"]
        return [n for n in (t.get("displayName"), t.get("shortDisplayName"), t.get("name"), t.get("abbreviation")) if n]

    return Partido(
        fuente="espn", id=str(e["id"]), url=_url_partido(liga, str(e["id"])),
        kickoff=_dt(e["date"]), home=h["team"]["displayName"], away=a["team"]["displayName"],
        home_score=score(h) if estado in (FT, AET, LIVE) else None,
        away_score=score(a) if estado in (FT, AET, LIVE) else None,
        estado=estado, alias=nombres(h) + ["|"] + nombres(a), liga=liga,
    )


def espn_scoreboard(http: Http, liga: str, desde: datetime, hasta: datetime) -> list[Partido]:
    """Todos los partidos de la liga entre dos fechas (UTC, inclusive, ±1 día de
    margen porque ESPN agrupa por día de la costa este de EUA).

    Una petición por día: desde el 2026-09-16 ESPN responde 400 ("Failed to get
    events endpoint") al rango `dates=D1-D2` en fútbol y NFL; el día suelto
    `dates=D` sigue funcionando. Un evento que aparece en dos días se cuenta una vez."""
    code = LIGAS[liga][0]
    dia = (desde - timedelta(days=1)).date()
    fin = (hasta + timedelta(days=1)).date()
    vistos: set[str] = set()
    out: list[Partido] = []
    while dia <= fin:
        data = http.get(f"{ESPN_API}/{code}/scoreboard?dates={dia:%Y%m%d}&limit=500")
        for e in data.get("events", []):
            if str(e["id"]) in vistos:
                continue
            vistos.add(str(e["id"]))
            out.append(_espn_partido(e, liga))
        dia += timedelta(days=1)
    return out


def _equipo_resumen(id_: str, nombre: str, alias: list[str], lado: str | None) -> dict:
    """Equipo de un resumen de alineaciones (espn_summary / uefa_resumen /
    tsdb_resumen): `jugadores` por id de la fuente, `filas` solo en TheSportsDB
    (sin ids); `titulares`/`banca` son nombres para mostrar, nunca para localizar."""
    return {"id": id_, "nombre": nombre, "alias": alias, "lado": lado, "titulares": [], "banca": [],
            "jugadores": {}, "filas": []}


def _agregar_jugador(eq: dict, pid: str, nombre: str, titular: bool, entro: bool | None) -> None:
    (eq["titulares"] if titular else eq["banca"]).append(nombre)
    # sin id la fila no se localiza por id; cruce.localizar_en_partido la ve por
    # nombre solo para marcar `discrepa` (¿id equivocado?).
    eq["jugadores"][pid or f"sin-id:{nombre}"] = {"id": pid, "nombre": nombre, "titular": titular, "entro": entro}


def espn_summary(http: Http, liga: str, event_id: str) -> dict:
    """Alineaciones y goles de un partido de fútbol con los ids de ESPN, para
    ubicar al jugador del sujeto por id (cruce.localizar_en_partido):
    {fuente: 'espn', equipos: {team.id: {id, nombre, alias, lado, titulares,
    banca, jugadores: {athlete.id: {id, nombre, titular, entro}}}}, goles:
    [{minuto, tipo, equipo, equipo_id, jugador, jugador_id, texto}], completo,
    publica_cambios, url}. El goleador es SOLO participants[0] (los siguientes
    son asistentes); `entro` = roster.subbedIn (ESPN sí publica cambios)."""
    code = LIGAS[liga][0]
    data = http.get(f"{ESPN_API}/{code}/summary?event={event_id}")
    equipos: dict[str, dict] = {}
    for r in data.get("rosters", []):
        t = r.get("team") or {}
        tid, nombre = str(t.get("id") or ""), t.get("displayName") or "?"
        alias = [n for n in (t.get("displayName"), t.get("shortDisplayName"), t.get("name"), t.get("abbreviation")) if n]
        eq = _equipo_resumen(tid, nombre, alias, r.get("homeAway"))
        for x in r.get("roster", []) or []:
            ath = x.get("athlete") or {}
            if not ath.get("displayName"):
                continue
            _agregar_jugador(eq, str(ath.get("id") or ""), ath["displayName"], bool(x.get("starter")), bool(x.get("subbedIn")))
        equipos[tid or nombre] = eq
    goles = []
    for k in data.get("keyEvents", []) or []:
        tipo = (k.get("type") or {}).get("text", "")
        if not k.get("scoringPlay") and "Goal" not in tipo:
            continue
        t = k.get("team") or {}
        autor = ((k.get("participants") or [{}])[0] or {}).get("athlete") or {}
        goles.append({
            "minuto": (k.get("clock") or {}).get("displayValue"),
            "tipo": tipo,  # "Goal", "Penalty - Scored", "Own Goal"…
            "equipo": t.get("displayName"), "equipo_id": str(t.get("id") or ""),
            "jugador": autor.get("displayName"), "jugador_id": str(autor.get("id") or ""),
            "texto": k.get("text", ""),
        })
    return {"fuente": "espn", "equipos": equipos, "goles": goles, "completo": True, "publica_cambios": True,
            "url": f"https://www.espn.com/soccer/lineups/_/gameId/{event_id}"}


def tsdb_resumen(http: Http, id_evento: str) -> dict:
    """Segunda fuente para accesorios de fútbol fuera de la UEFA: alineaciones
    (lookuplineup: strSubstitute No = titular) y goles (lookuptimeline:
    strTimeline "Goal"; "Own Goal" en el detalle) de TheSportsDB, con la forma
    de espn_summary pero SIN ids: cada equipo trae `filas` [{nombre, titular}]
    y cruce.localizar_en_partido solo acepta un nombre normalizado idéntico y
    único dentro del equipo (`ambiguo` si se repite).
    OJO: la capa gratuita RECORTA ambos listados a 5 filas (`completo: False`):
    solo sirve para confirmar presencias (titular YES, gol YES), nunca ausencias.
    Tampoco trae sustituciones (`publica_cambios: False`)."""
    lineup = http.get(f"{TSDB_API}/lookuplineup.php?id={id_evento}").get("lineup") or []
    equipos: dict[str, dict] = {}

    def equipo(nombre: str | None) -> dict:
        nombre = nombre or "?"
        return equipos.setdefault(nombre, _equipo_resumen("", nombre, [nombre], None))

    for x in lineup:
        eq, n = equipo(x.get("strTeam")), x.get("strPlayer") or ""
        titular = (x.get("strSubstitute") or "No") == "No"
        (eq["titulares"] if titular else eq["banca"]).append(n)
        eq["filas"].append({"nombre": n, "titular": titular})
    timeline = http.get(f"{TSDB_API}/lookuptimeline.php?id={id_evento}").get("timeline") or []
    goles = []
    for t in timeline:
        if (t.get("strTimeline") or "").lower() != "goal":
            continue
        detalle = t.get("strTimelineDetail") or "Goal"
        equipo(t.get("strTeam"))  # un goleador fuera de la alineación recortada también prueba presencia
        goles.append({"minuto": f"{t.get('intTime')}'", "tipo": detalle, "equipo": t.get("strTeam"), "equipo_id": "",
                      "jugador": t.get("strPlayer"), "jugador_id": "", "texto": f"{t.get('strPlayer')} ({detalle})"})
    return {"fuente": "tsdb", "equipos": equipos, "goles": goles, "completo": False, "publica_cambios": False,
            "url": f"https://www.thesportsdb.com/event/{id_evento}"}


# ── UEFA (match.uefa.com: fuente oficial de Champions/Europa League) ─────────

UEFA_API = "https://match.uefa.com/v5"
# subcategoría → competitionId de la UEFA. Solo estas ligas usan la UEFA como
# segunda fuente (alineaciones completas + goleadores oficiales).
UEFA_COMPETICION: dict[str, str] = {"Champions League": "1", "Europa League": "14"}


def _uefa_nombres(team: dict) -> list[str]:
    tr = (team.get("translations") or {})
    nombres = [team.get("internationalName"), (tr.get("displayOfficialName") or {}).get("EN"),
               (tr.get("displayName") or {}).get("EN"), (tr.get("shortName") or {}).get("EN")]
    out: list[str] = []
    for n in nombres:
        if n and n not in out:
            out.append(n)
    return out


def _uefa_id(v) -> str:
    """Id de la UEFA como string: llega como str o como int según el endpoint."""
    return "" if v in (None, "") else str(v)


def uefa_partidos(http: Http, liga: str, desde: datetime, hasta: datetime) -> list[dict]:
    """Partidos oficiales de la competencia entre dos fechas: id, kickoff, nombres
    (con alias) e id de cada equipo (`home_id`/`away_id`), marcador, estado y
    goleadores con `jugador_id` (player.id) y `equipo_id` (teamId de la fila,
    nunca player.clubId, que es el club ACTUAL del jugador)."""
    comp = UEFA_COMPETICION[liga]
    season = desde.year + 1 if desde.month >= 7 else desde.year  # 2026/27 → 2027
    d1, d2 = (desde - timedelta(days=1)).strftime("%Y-%m-%d"), (hasta + timedelta(days=1)).strftime("%Y-%m-%d")
    data = http.get(f"{UEFA_API}/matches?competitionId={comp}&fromDate={d1}&toDate={d2}&limit=100&offset=0&order=ASC&seasonYear={season}")
    out = []
    for m in data if isinstance(data, list) else []:
        total = (m.get("score") or {}).get("total") or {}
        home_t, away_t = m.get("homeTeam") or {}, m.get("awayTeam") or {}
        home_id, away_id = _uefa_id(home_t.get("id")), _uefa_id(away_t.get("id"))
        goles = []
        for s in ((m.get("playerEvents") or {}).get("scorers") or []):
            p = s.get("player") or {}
            tipo = s.get("goalType") or "SCORED"
            equipo_id = _uefa_id(s.get("teamId"))
            equipo = (home_t.get("internationalName") if equipo_id and equipo_id == home_id
                      else away_t.get("internationalName") if equipo_id and equipo_id == away_id else None)
            goles.append({"minuto": (s.get("time") or {}).get("minute"), "tipo": "Own Goal" if "OWN" in tipo else tipo,
                          "equipo": equipo, "equipo_id": equipo_id,
                          "jugador": p.get("internationalName"), "jugador_id": _uefa_id(p.get("id")),
                          "texto": f"{p.get('internationalName')} ({tipo})"})
        out.append({
            "id": str(m.get("id")), "kickoff": _dt(((m.get("kickOffTime") or {}).get("dateTime")) or "1970-01-01T00:00:00Z"),
            "home": _uefa_nombres(home_t), "away": _uefa_nombres(away_t), "home_id": home_id, "away_id": away_id,
            "home_score": total.get("home"), "away_score": total.get("away"), "estado": m.get("status"), "goles": goles,
        })
    return out


def uefa_resumen(http: Http, liga: str, partido: dict) -> dict:
    """Alineaciones oficiales (11 titulares + banca) y goleadores de un partido
    de la UEFA, con la forma de espn_summary: equipos por `team.id` (str) con
    alias por lado (lineups + uefa_partidos) y `jugadores` por player.id (str).
    `completo: True`: una ausencia en `field`/`bench` sí significa que no fue
    titular / no fue convocado. No trae sustituciones (`publica_cambios: False`,
    `entro` None)."""
    data = http.get(f"{UEFA_API}/matches/{partido['id']}/lineups")
    equipos: dict[str, dict] = {}
    for lado, clave in (("homeTeam", "home"), ("awayTeam", "away")):
        t = data.get(lado) or {}
        team = t.get("team") or {}
        tid = _uefa_id(team.get("id")) or _uefa_id(partido.get(f"{clave}_id"))
        alias: list[str] = []
        for n in _uefa_nombres(team) + list(partido.get(clave) or []):
            if n and n not in alias:
                alias.append(n)
        nombre = team.get("internationalName") or (alias[0] if alias else lado)
        eq = _equipo_resumen(tid, nombre, alias, clave)
        for titular, filas in ((True, t.get("field") or []), (False, t.get("bench") or [])):
            for x in filas:
                p = x.get("player") or {}
                _agregar_jugador(eq, _uefa_id(p.get("id")), p.get("internationalName") or "", titular, None)
        equipos[tid or nombre] = eq
    slug = "uefachampionsleague" if UEFA_COMPETICION.get(liga) == "1" else "uefaeuropaleague"
    return {"fuente": "uefa", "equipos": equipos, "goles": partido.get("goles") or [], "completo": True,
            "publica_cambios": False, "url": f"https://www.uefa.com/{slug}/match/{partido['id']}/"}


# Categorías ofensivas del box score de ESPN (NFL) de las que salen las props.
# El resto (defensive, interceptions, kickReturns, puntReturns, kicking,
# punting) solo prueba que el jugador estuvo en el partido.
NFL_CATEGORIAS_OFENSIVAS = ("passing", "rushing", "receiving")


def espn_boxscore_nfl(http: Http, liga: str, event_id: str) -> dict:
    """Box score de un partido de NFL con TODAS las categorías, indexado por
    `athlete.id` (dos jugadores con el mismo nombre ya no se funden):
    {jugadores: {id: {id, nombre, abbr, equipo, equipo_id, passing: {...},
    rushing: {...}, fumbles: {...}, defensive: {...}, kickReturns: {...}, ...}},
    equipos: {abbr: displayName}, injuries: {abbr: [{id, nombre, estado}]},
    estado, url}. Cada categoría trae `keys`, así que las stats van por key.
    Solo aparecen los jugadores con alguna estadística; el box score NO publica
    la lista de inactivos (ausente ≠ inactivo confirmado) e `injuries` es el
    reporte de lesiones, no la lista de inactivos: solo sirve como dato."""
    code = LIGAS[liga][0]
    data = http.get(f"{ESPN_API}/{code}/summary?event={event_id}")
    jugadores: dict[str, dict] = {}
    equipos: dict[str, str] = {}
    for team in (data.get("boxscore") or {}).get("players", []):
        t = team.get("team") or {}
        abbr, equipo = t.get("abbreviation") or "?", t.get("displayName") or "?"
        equipos[abbr] = equipo
        for cat in team.get("statistics", []):
            nombre_cat = cat.get("name")
            if not nombre_cat:
                continue
            keys = cat.get("keys") or cat.get("labels") or []
            for a in cat.get("athletes", []):
                ath = a.get("athlete") or {}
                nombre = ath.get("displayName")
                if not nombre:
                    continue
                # sin id (no pasa en la muestra real) la fila no se puede
                # localizar por id; cruce.localizar_jugador la ve por nombre
                # solo para marcar `discrepa`.
                clave = str(ath["id"]) if ath.get("id") else f"sin-id:{abbr}:{nombre}"
                j = jugadores.setdefault(clave, {"id": str(ath.get("id") or ""), "nombre": nombre, "abbr": abbr,
                                                 "equipo": equipo, "equipo_id": str(t.get("id") or "")})
                j[nombre_cat] = dict(zip(keys, a.get("stats", [])))
    injuries: dict[str, list[dict]] = {}
    for t in data.get("injuries") or []:
        abbr = (t.get("team") or {}).get("abbreviation") or "?"
        injuries[abbr] = [{"id": str((i.get("athlete") or {}).get("id") or ""),
                           "nombre": (i.get("athlete") or {}).get("displayName") or "",
                           "estado": i.get("status") or ((i.get("type") or {}).get("description") or "")}
                          for i in t.get("injuries") or []]
    tipo = ((data.get("header") or {}).get("competitions") or [{}])[0].get("status", {}).get("type", {})
    estado = _ESPN_ESTADOS.get(tipo.get("name"), FT if tipo.get("completed") else UNKNOWN)
    return {"jugadores": jugadores, "equipos": equipos, "injuries": injuries, "estado": estado,
            "url": f"https://www.espn.com/nfl/boxscore/_/gameId/{event_id}"}


# ── CBS Sports (segunda fuente de props NFL) ─────────────────────────────────

# Abreviaturas de ESPN → CBS cuando difieren.
CBS_ABBR = {"WSH": "WAS", "JAX": "JAC"}
# Secciones con stats de props (primera celda de la cabecera, en minúsculas).
# Las demás (Defense, Kicking, Punting, Kickoff Returns, Punt Returns) solo
# cuentan como presencia del jugador.
_CBS_KEYS = {
    "passing": {"YDS": "passingYards", "TD": "passingTouchdowns", "INT": "interceptions"},
    "rushing": {"ATT": "rushingAttempts", "YDS": "rushingYards", "TD": "rushingTouchdowns"},
    "receiving": {"TAR": "receivingTargets", "REC": "receptions", "YDS": "receivingYards", "TD": "receivingTouchdowns"},
}
_RE_CBS_CABECERA = re.compile(r'<tr class="header-row">(.*?)</tr>', re.S)
_RE_CBS_CELDA = re.compile(r'<td class="(?:name|number)-element">\s*(.*?)\s*</td>', re.S)
_RE_CBS_FILA = re.compile(r'<tr class="[^"]*data-row[^"]*">', re.S)
_RE_CBS_EQUIPO = re.compile(r'data-team-abbr="([A-Z]+)"')
_RE_CBS_JUGADOR = re.compile(r'/nfl/players/(\d+)/([a-z0-9-]+)/')


def cbs_url_boxscore(kickoff_utc: datetime, away_abbr: str, home_abbr: str) -> str:
    """URL del box score de CBS: fecha local del este de EUA + abreviaturas."""
    from zoneinfo import ZoneInfo

    fecha = kickoff_utc.astimezone(ZoneInfo("America/New_York")).strftime("%Y%m%d")
    a, h = CBS_ABBR.get(away_abbr, away_abbr), CBS_ABBR.get(home_abbr, home_abbr)
    return f"https://www.cbssports.com/nfl/gametracker/boxscore/NFL_{fecha}_{a}@{h}/"


def parsear_cbs_boxscore(html: str, url: str = "") -> dict:
    """Box score de CBS → {jugadores: {id CBS: {id, nombre, slug, abbr, equipo,
    secciones: [...], passing?: {...}, rushing?: {...}, receiving?: {...}}}, url}.
    El id y el nombre salen del enlace /nfl/players/{id}/{slug}/ (el texto del
    enlace es corto: "J. Allen"); el equipo, de `data-team-abbr` de la fila
    ('?' = no publicado, no "otro equipo"). La presencia se toma de TODAS las
    secciones (también Defense y devoluciones); las stats, con keys de ESPN, solo
    de Passing/Rushing/Receiving. CBS no publica fumbles perdidos."""
    cabeceras = [(m.start(), [re.sub(r"\s+", " ", c).strip() for c in _RE_CBS_CELDA.findall(m.group(1))])
                 for m in _RE_CBS_CABECERA.finditer(html)]
    filas = [m.start() for m in _RE_CBS_FILA.finditer(html)]
    jugadores: dict[str, dict] = {}
    for i, ini in enumerate(filas):
        # la sección de la fila es la de la última cabecera antes de ella
        labels = next((ls for p, ls in reversed(cabeceras) if p < ini), None)
        if not labels:
            continue
        sec = labels[0].lower()
        # el enlace del jugador debe estar en ESTA fila (antes de la siguiente)
        link = _RE_CBS_JUGADOR.search(html, ini, filas[i + 1] if i + 1 < len(filas) else len(html))
        if not link:
            continue
        pid, slug = link.group(1), link.group(2)
        eq = _RE_CBS_EQUIPO.search(html, ini, link.start())
        abbr = eq.group(1) if eq else "?"
        j = jugadores.setdefault(pid, {"id": pid, "nombre": " ".join(p.capitalize() for p in slug.split("-")),
                                       "slug": slug, "abbr": abbr, "equipo": abbr, "secciones": []})
        if j["abbr"] == "?" and abbr != "?":
            j["abbr"] = j["equipo"] = abbr
        if sec not in j["secciones"]:
            j["secciones"].append(sec)
        if sec not in _CBS_KEYS:
            continue
        fin = html.find("</tr>", link.end())
        celdas = [re.sub(r"\s+", " ", c).strip() for c in _RE_CBS_CELDA.findall(html[link.end():fin])]
        stats = {}
        for label, valor in zip(labels[1:], celdas):
            key = _CBS_KEYS[sec].get(label)
            if key:
                stats[key] = valor
        j[sec] = stats
    return {"jugadores": jugadores, "url": url}


def cbs_boxscore_nfl(http: Http, kickoff_utc: datetime, away_abbr: str, home_abbr: str) -> dict:
    url = cbs_url_boxscore(kickoff_utc, away_abbr, home_abbr)
    return parsear_cbs_boxscore(http.get_text(url), url)


# ── TheSportsDB ──────────────────────────────────────────────────────────────

def _tsdb_partido(e: dict) -> Partido:
    ts = e.get("strTimestamp") or f"{e.get('dateEvent')}T{e.get('strTime') or '00:00:00'}"
    estado_raw = e.get("strStatus") or ""
    estado = _TSDB_ESTADOS.get(estado_raw, UNKNOWN)
    hs, as_ = e.get("intHomeScore"), e.get("intAwayScore")
    if estado == UNKNOWN and hs not in (None, "") and as_ not in (None, ""):
        estado = FT  # algunos eventos viejos traen marcador sin status
    return Partido(
        fuente="tsdb", id=str(e["idEvent"]), url=f"https://www.thesportsdb.com/event/{e['idEvent']}",
        kickoff=_dt(ts), home=e.get("strHomeTeam", ""), away=e.get("strAwayTeam", ""),
        home_score=int(hs) if hs not in (None, "") else None,
        away_score=int(as_) if as_ not in (None, "") else None,
        estado=estado, liga=e.get("strLeague", ""),
    )


def _tsdb_eventos(http: Http, endpoint: str, q: str, kickoff: datetime, tolerancia_h: float) -> Partido | None:
    data = http.get(f"{TSDB_API}/{endpoint}.php?e={urllib.parse.quote(q)}")
    for e in data.get("event") or []:
        try:
            p = _tsdb_partido(e)
        except (KeyError, ValueError):
            continue
        if abs((p.kickoff - kickoff).total_seconds()) <= tolerancia_h * 3600:
            return p
    return None


def tsdb_buscar(http: Http, liga: str, homes: list[str], aways: list[str], kickoff: datetime,
                tolerancia_h: float = 6, max_consultas: int = 8) -> tuple[Partido | None, int]:
    """Busca el partido probando variantes de nombre. La capa gratuita de
    searchevents devuelve UN resultado (el más viejo), así que si el nombre es
    correcto pero el partido no aparece, se pasa a searchfilename, que incluye
    liga y fecha y por eso es unívoco. Devuelve (partido, consultas hechas)."""
    liga_tsdb = LIGAS[liga][2]
    consultas = 0
    pares = [(h, a) for i, h in enumerate(homes[:3]) for j, a in enumerate(aways[:3]) if i + j <= 2]
    pares.sort(key=lambda t: homes.index(t[0]) + aways.index(t[1]))
    for h, a in pares:
        if consultas >= max_consultas:
            break
        consultas += 1
        p = _tsdb_eventos(http, "searchevents", f"{h}_vs_{a}".replace(" ", "_"), kickoff, tolerancia_h)
        if p is not None:
            return p, consultas
    fechas = [kickoff.strftime("%Y-%m-%d"), (kickoff - timedelta(days=1)).strftime("%Y-%m-%d")]
    for h, a in pares[:3]:
        for f in fechas:
            if consultas >= max_consultas:
                return None, consultas
            consultas += 1
            p = _tsdb_eventos(http, "searchfilename", f"{liga_tsdb} {f} {h} vs {a}", kickoff, tolerancia_h)
            if p is not None:
                return p, consultas
    return None, consultas
