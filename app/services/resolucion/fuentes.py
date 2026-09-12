"""Clientes de solo lectura de resultados de fútbol (stdlib, sin API key).

ESPN  — site.api.espn.com: scoreboard por liga y rango de fechas (jornada
        completa, marcador, estado) y summary por evento (alineaciones con
        titulares, eventos clave con goles). Bloquea User-Agents de navegador y
        de Python; acepta el de curl.
TSDB  — thesportsdb.com API v1 con la key pública `3`. La capa gratuita recorta
        los listados (eventsday devuelve 3 filas), así que solo se usa la
        búsqueda por partido (`searchevents.php?e=Local_vs_Visitante`), que sí
        devuelve el marcador final. Sirve como segunda fuente independiente.
"""
from __future__ import annotations

import json
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
    margen porque ESPN agrupa por día de la costa este de EUA)."""
    code = LIGAS[liga][0]
    d1 = (desde - timedelta(days=1)).strftime("%Y%m%d")
    d2 = (hasta + timedelta(days=1)).strftime("%Y%m%d")
    data = http.get(f"{ESPN_API}/{code}/scoreboard?dates={d1}-{d2}&limit=500")
    return [_espn_partido(e, liga) for e in data.get("events", [])]


def espn_summary(http: Http, liga: str, event_id: str) -> dict:
    """Alineaciones (titulares y banca por equipo) y goles de un partido."""
    code = LIGAS[liga][0]
    data = http.get(f"{ESPN_API}/{code}/summary?event={event_id}")
    equipos: dict[str, dict[str, list[str]]] = {}
    for r in data.get("rosters", []):
        nombre = r.get("team", {}).get("displayName", "?")
        titulares = [x["athlete"]["displayName"] for x in r.get("roster", []) if x.get("starter")]
        banca = [x["athlete"]["displayName"] for x in r.get("roster", []) if not x.get("starter")]
        equipos[nombre] = {"titulares": titulares, "banca": banca}
    goles = []
    for k in data.get("keyEvents", []) or []:
        tipo = (k.get("type") or {}).get("text", "")
        if not k.get("scoringPlay") and "Goal" not in tipo:
            continue
        autores = [p.get("athlete", {}).get("displayName") for p in k.get("participants", [])]
        goles.append({
            "minuto": (k.get("clock") or {}).get("displayValue"),
            "tipo": tipo,  # "Goal", "Penalty - Scored", "Own Goal"…
            "equipo": (k.get("team") or {}).get("displayName"),
            "jugador": autores[0] if autores else None,
            "texto": k.get("text", ""),
        })
    return {"equipos": equipos, "goles": goles, "url": f"https://www.espn.com/soccer/lineups/_/gameId/{event_id}"}


# Categorías del box score de ESPN (NFL) que usan las props: cada una trae
# `keys` con los nombres de estadística, así que se guardan por key.
_NFL_CATEGORIAS = ("passing", "rushing", "receiving", "fumbles")


def espn_boxscore_nfl(http: Http, liga: str, event_id: str) -> dict:
    """Estadísticas por jugador de un partido de NFL: {jugadores: {nombre:
    {equipo, passing: {...}, rushing: {...}, receiving: {...}, fumbles: {...}}},
    estado, url}. Solo aparecen los jugadores con alguna estadística registrada:
    un jugador ausente del box score no participó (inactivo)."""
    code = LIGAS[liga][0]
    data = http.get(f"{ESPN_API}/{code}/summary?event={event_id}")
    jugadores: dict[str, dict] = {}
    for team in (data.get("boxscore") or {}).get("players", []):
        equipo = (team.get("team") or {}).get("displayName", "?")
        for cat in team.get("statistics", []):
            nombre_cat = cat.get("name")
            if nombre_cat not in _NFL_CATEGORIAS:
                continue
            keys = cat.get("keys") or cat.get("labels") or []
            for a in cat.get("athletes", []):
                nombre = (a.get("athlete") or {}).get("displayName")
                if not nombre:
                    continue
                stats = dict(zip(keys, a.get("stats", [])))
                j = jugadores.setdefault(nombre, {"equipo": equipo})
                j[nombre_cat] = stats
    tipo = ((data.get("header") or {}).get("competitions") or [{}])[0].get("status", {}).get("type", {})
    estado = _ESPN_ESTADOS.get(tipo.get("name"), FT if tipo.get("completed") else UNKNOWN)
    return {"jugadores": jugadores, "estado": estado, "url": f"https://www.espn.com/nfl/boxscore/_/gameId/{event_id}"}


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
