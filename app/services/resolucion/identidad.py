"""Búsqueda con red de los ids de un jugador en cada fuente (ESPN, CBS, UEFA)
para llenar `sujeto.ids` al sembrar (`sembrar-mercados.py identificar`) y en el
backfill de mercados ya sembrados.

Regla: nunca adivinar. El jugador se busca en el plantel del EQUIPO del sujeto y
solo vale un nombre normalizado idéntico y único (sin sufijos Jr./III); 0 o más
de 1 candidatos es error con la lista de parecidos, jamás un "el más cercano".
Después se cruzan dorsal (y posición en NFL) entre fuentes, porque nombre +
equipo es lo único que liga los ids de una fuente con los de otra.

Endpoints (GET públicos verificados el 2026-09-14):
  ESPN equipos  {ESPN_API}/{code}/teams → sports[0].leagues[0].teams[].team
  ESPN plantel  NFL: football/nfl/teams/{abbr}/roster (athletes[].items[] por grupo);
                fútbol: {code}/teams/{id}/roster (athletes[] plano)
  CBS           índice https://www.cbssports.com/nfl/teams/ (abbr → slug) y
                /nfl/teams/{ABBR}/{slug}/roster/ (enlace /nfl/players/{id}/{slug}/;
                la celda anterior es el dorsal y la siguiente la posición)
  UEFA          comp.uefa.com/v2/teams (id de equipo) y compstats.uefa.com
                player-ranking por teamId (plantel; `teamId` de la fila, nunca
                player.clubId). compstats puede omitir inscritos sin minutos:
                respaldo con las alineaciones de partidos previos del club.
"""
from __future__ import annotations

import html as html_lib
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from .cruce import UMBRAL, normalizar, similitud
from .fuentes import CBS_ABBR, ESPN_API, LIGAS, UEFA_API, UEFA_COMPETICION, Http, _dt, _uefa_nombres, deporte
from .sujeto import IDS_REQUERIDOS, normalizar_sujeto

CBS_BASE = "https://www.cbssports.com"
UEFA_COMP_API = "https://comp.uefa.com/v2"
UEFA_STATS_API = "https://compstats.uefa.com/v1"
MARGEN = 0.15  # ventaja mínima del mejor equipo sobre el segundo (igual que cruce._key_de_equipo)

_SUFIJOS = {"jr", "sr", "ii", "iii", "iv"}
_RE_CBS_INDICE = re.compile(r"/nfl/teams/([A-Z]{2,3})/([a-z0-9-]+)/")
_CBS_NO_SLUG = {"roster", "schedule", "stats", "injuries", "depth-chart", "transactions", "news",
                "tickets", "odds", "photos", "videos", "draft"}
_RE_CBS_JUGADOR = re.compile(r"/nfl/players/(\d+)/([a-z0-9-]+)/")
_RE_TR = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_RE_TD = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
_RE_TAG = re.compile(r"<[^>]+>")
_POS_NFL = {"PK": "K", "OT": "T", "OG": "G"}  # alias ESPN ↔ CBS de la misma posición
# Grupo de posición NFL: ESPN y CBS rotulan distinto a la misma persona (S/SAF,
# DT/DE, CB/DB, LB/OLB, FB/RB). Dentro del grupo es aviso; entre grupos, error.
# QB, WR y TE quedan solos (pases de TD exige QB).
_GRUPO_POS_NFL = {
    **dict.fromkeys(("S", "SAF", "FS", "SS", "DB", "CB"), "DB"),
    **dict.fromkeys(("LB", "OLB", "ILB", "MLB"), "LB"),
    **dict.fromkeys(("DE", "DT", "DL", "NT"), "DL"),
    **dict.fromkeys(("RB", "FB"), "RB"),
    **dict.fromkeys(("T", "G", "C", "OL"), "OL"),
}
_ERRORES_RED = (RuntimeError, KeyError, TypeError, ValueError, AttributeError, IndexError)


# ── nombres y candidatos (puro) ──────────────────────────────────────────────

def clave_nombre(nombre: str) -> str:
    """normalizar() sin sufijos generacionales finales (Marvin Harrison Jr.)."""
    toks = normalizar(nombre or "").split()
    while len(toks) > 2 and toks[-1] in _SUFIJOS:
        toks.pop()
    return " ".join(toks)


def _clave(nombre: str, fuente: str) -> str:
    # CBS solo trae el slug ("dandre-swift"): se compara sin espacios, porque
    # normalizar("D'Andre Swift") = "d andre swift".
    if fuente == "cbs":
        return clave_nombre((nombre or "").replace("-", " ")).replace(" ", "")
    return clave_nombre(nombre)


def candidatos_exactos(plantel: list[dict], jugador: str, fuente: str = "espn") -> list[dict]:
    objetivo = _clave(jugador, fuente)
    por_id: dict[str, dict] = {}
    for p in plantel:
        if objetivo and objetivo in {_clave(n, fuente) for n in p.get("nombres") or []}:
            por_id.setdefault(str(p["id"]), p)
    return list(por_id.values())


def _lista(jugadores: list[dict]) -> str:
    return "; ".join(f"{p['id']} {p.get('nombre')} ({p.get('posicion') or '?'} #{p.get('jersey') or '?'})"
                     for p in jugadores[:8])


def _parecidos(plantel: list[dict], jugador: str) -> list[dict]:
    """Solo para el mensaje de error (nunca se elige uno): comparten un token."""
    toks = {t for t in clave_nombre(jugador).split() if len(t) >= 3}
    return [p for p in plantel
            if toks & {t for n in p.get("nombres") or [] for t in clave_nombre(n.replace("-", " ")).split()}]


def candidato_unico(plantel: list[dict], jugador: str, fuente: str = "espn") -> tuple[dict | None, str]:
    """(jugador, '') si hay exactamente un nombre idéntico en el plantel; si no,
    (None, motivo con los candidatos o parecidos). Nunca fuzzy."""
    exactos = candidatos_exactos(plantel, jugador, fuente)
    if len(exactos) == 1:
        return exactos[0], ""
    if exactos:
        return None, f"{len(exactos)} jugadores con el nombre exacto '{jugador}': {_lista(exactos)}"
    parecidos = _parecidos(plantel, jugador)
    return None, (f"'{jugador}' no está en el plantel ({len(plantel)} jugadores)"
                  + (f"; parecidos (no se elige ninguno): {_lista(parecidos)}" if parecidos else ""))


def equipo_unico(candidatos: list[dict], nombre: str) -> tuple[dict | None, str]:
    """Equipo con similitud ≥ UMBRAL contra alguno de sus alias y ventaja ≥ MARGEN
    sobre el segundo; si no, (None, motivo)."""
    puntuados = sorted(
        ((max((similitud(nombre, a) for a in c.get("alias") or [] if a), default=0.0), i) for i, c in enumerate(candidatos)),
        reverse=True,
    )
    if not puntuados or puntuados[0][0] < UMBRAL:
        mejor = f" (mejor: {candidatos[puntuados[0][1]]['nombre']}, {puntuados[0][0]:.2f})" if puntuados else ""
        return None, f"'{nombre}' no coincide con ningún equipo{mejor}"
    if len(puntuados) > 1 and puntuados[0][0] - puntuados[1][0] < MARGEN:
        a, b = candidatos[puntuados[0][1]], candidatos[puntuados[1][1]]
        return None, f"'{nombre}' es ambiguo entre {a['nombre']} y {b['nombre']}"
    return candidatos[puntuados[0][1]], ""


def _texto_html(s: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_RE_TAG.sub(" ", s or ""))).strip()


def parsear_roster_cbs(html: str) -> list[dict]:
    """Plantel de CBS: una fila por jugador (el enlace sale dos veces por fila:
    nombre corto y largo; se deduplica por id)."""
    out: dict[str, dict] = {}
    for fila in _RE_TR.finditer(html or ""):
        celdas = _RE_TD.findall(fila.group(1))
        for i, celda in enumerate(celdas):
            m = _RE_CBS_JUGADOR.search(celda)
            if not m:
                continue
            pid, slug = m.groups()
            out.setdefault(pid, {
                "id": pid, "nombre": " ".join(p.capitalize() for p in slug.split("-")), "nombres": [slug],
                "slug": slug, "jersey": _texto_html(celdas[i - 1]) if i > 0 else "",
                "posicion": _texto_html(celdas[i + 1]) if i + 1 < len(celdas) else "",
            })
            break
    return list(out.values())


def _dorsal(v) -> str:
    m = re.search(r"\d+", str(v or ""))
    return str(int(m.group())) if m else ""


def _pos_nfl(v) -> str:
    p = str(v or "").strip().upper()
    return _POS_NFL.get(p, p)


def _grupo_pos_nfl(v) -> str:
    p = _pos_nfl(v)
    return _GRUPO_POS_NFL.get(p, p)


def cruzar(espn: dict, otro: dict, fuente: str, con_posicion: bool) -> tuple[list[str], list[str]]:
    """(errores, avisos) del chequeo cruzado dorsal (y posición NFL) ESPN ↔ otra fuente."""
    errores: list[str] = []
    avisos: list[str] = []
    quien = f"ESPN {espn['id']} {espn.get('nombre')} / {fuente} {otro['id']} {otro.get('nombre')}"
    je, jo = _dorsal(espn.get("jersey")), _dorsal(otro.get("jersey"))
    if je and jo and je != jo:
        errores.append(f"dorsal distinto: ESPN #{je} ≠ {fuente} #{jo} ({quien}): ¿otra persona? verificar a mano")
    elif not (je and jo):
        avisos.append(f"sin dorsal para cruzar ESPN y {fuente} ({quien})")
    if con_posicion:
        pe, po = _pos_nfl(espn.get("posicion")), _pos_nfl(otro.get("posicion"))
        if pe and po and pe != po and _grupo_pos_nfl(pe) == _grupo_pos_nfl(po):
            avisos.append(f"posición con otra etiqueta: ESPN {pe} / {fuente} {po}, mismo grupo {_grupo_pos_nfl(pe)} ({quien})")
        elif pe and po and pe != po:
            errores.append(f"posición distinta: ESPN {pe} ≠ {fuente} {po} ({quien}): verificar a mano")
        elif not (pe and po):
            avisos.append(f"sin posición para cruzar ESPN y {fuente} ({quien})")
    return errores, avisos


# ── ESPN ─────────────────────────────────────────────────────────────────────

def equipos_espn(http: Http, liga: str) -> list[dict]:
    code = LIGAS[liga][0]
    data = http.get(f"{ESPN_API}/{code}/teams")
    out = []
    for lg in ((data.get("sports") or [{}])[0].get("leagues") or []):
        for t in lg.get("teams") or []:
            team = t.get("team") or {}
            if not team.get("id"):
                continue
            alias = [n for n in (team.get("displayName"), team.get("shortDisplayName"), team.get("name"),
                                 team.get("abbreviation")) if n]
            out.append({"id": str(team["id"]), "abbr": team.get("abbreviation") or "",
                        "nombre": team.get("displayName") or "", "alias": alias})
    return out


def plantel_espn(http: Http, liga: str, equipo: dict) -> list[dict]:
    code = LIGAS[liga][0]
    if deporte(liga) == "nfl":
        url = f"{ESPN_API}/{code}/teams/{equipo['abbr'].lower()}/roster"
    else:
        url = f"{ESPN_API}/{code}/teams/{equipo['id']}/roster"
    data = http.get(url)
    out: dict[str, dict] = {}
    for a in data.get("athletes") or []:
        # NFL agrupa (offense, defense, practiceSquad…) en items[]; fútbol es plano
        for x in (a.get("items") if isinstance(a.get("items"), list) else [a]):
            if not x.get("id"):
                continue
            out.setdefault(str(x["id"]), {
                "id": str(x["id"]), "nombre": x.get("displayName") or x.get("fullName") or "",
                "nombres": [n for n in (x.get("displayName"), x.get("fullName")) if n],
                "posicion": (x.get("position") or {}).get("abbreviation") or "",
                "jersey": str(x.get("jersey") or ""),
            })
    return list(out.values())


# ── CBS (NFL) ────────────────────────────────────────────────────────────────

def slugs_cbs(http: Http) -> dict[str, str]:
    """Abreviatura CBS → slug del equipo, del índice de equipos."""
    conteo: dict[str, Counter] = defaultdict(Counter)
    for abbr, slug in _RE_CBS_INDICE.findall(http.get_text(f"{CBS_BASE}/nfl/teams/")):
        if slug not in _CBS_NO_SLUG:
            conteo[abbr][slug] += 1
    return {abbr: c.most_common(1)[0][0] for abbr, c in conteo.items()}


def plantel_cbs(http: Http, abbr_espn: str) -> list[dict]:
    abbr = CBS_ABBR.get(abbr_espn, abbr_espn)
    slug = slugs_cbs(http).get(abbr)
    if not slug:
        raise RuntimeError(f"{abbr} no aparece en el índice de equipos de CBS")
    return parsear_roster_cbs(http.get_text(f"{CBS_BASE}/nfl/teams/{abbr}/{slug}/roster/"))


# ── UEFA ─────────────────────────────────────────────────────────────────────

def temporada_uefa(fecha: datetime) -> int:
    """Año final de la temporada, igual que fuentes.uefa_partidos (2026/27 → 2027)."""
    return fecha.year + 1 if fecha.month >= 7 else fecha.year


def equipos_uefa(http: Http, liga: str, temporada: int) -> list[dict]:
    comp = UEFA_COMPETICION[liga]
    out = []
    for offset in range(0, 500, 100):
        data = http.get(f"{UEFA_COMP_API}/teams?competitionId={comp}&seasonYear={temporada}&limit=100&offset={offset}")
        filas = data if isinstance(data, list) else []
        for t in filas:
            if t.get("id") is not None:
                out.append({"id": str(t["id"]), "nombre": t.get("internationalName") or "", "alias": _uefa_nombres(t)})
        if len(filas) < 100:
            break
    return out


def plantel_uefa(http: Http, liga: str, team_id: str, temporada: int) -> list[dict]:
    comp = UEFA_COMPETICION[liga]
    out: dict[str, dict] = {}
    for offset in range(0, 300, 100):
        data = http.get(f"{UEFA_STATS_API}/player-ranking?competitionId={comp}&seasonYear={temporada}&teamId={team_id}"
                        f"&limit=100&offset={offset}&stats=minutes_played_official&optionalFields=PLAYER,TEAM")
        filas = data if isinstance(data, list) else []
        for r in filas:
            if str(r.get("teamId")) != str(team_id):
                continue  # el equipo de la fila manda; player.clubId es el club ACTUAL
            p = r.get("player") or {}
            pid = str(p.get("id") or r.get("playerId") or "")
            if pid:
                out.setdefault(pid, {"id": pid, "nombre": p.get("internationalName") or "",
                                     "nombres": [n for n in (p.get("internationalName"),) if n],
                                     "posicion": p.get("fieldPosition") or "", "jersey": str(p.get("clubJerseyNumber") or "")})
        if len(filas) < 100:
            break
    return list(out.values())


def _antes_de(m: dict, hasta: datetime) -> bool:
    """El partido empezó antes de `hasta` (sin kickoff legible: se conserva)."""
    iso = (m.get("kickOffTime") or {}).get("dateTime")
    try:
        return not iso or _dt(iso) < hasta
    except (ValueError, AttributeError):
        return True


def plantel_uefa_alineaciones(http: Http, liga: str, team_id: str, temporada: int, hasta: datetime,
                              max_partidos: int = 4, max_paginas: int = 10) -> list[dict]:
    """Respaldo: jugadores (titulares y banca) de las últimas `max_partidos`
    alineaciones oficiales del club en la competencia antes de `hasta`. Orden
    DESC y paginado: en ASC la primera página se llena con las rondas previas y
    nunca llega a los partidos recientes del club."""
    comp = UEFA_COMPETICION[liga]
    d1 = f"{temporada - 1}-06-01"
    d2 = hasta.strftime("%Y-%m-%d")
    propios: list[dict] = []
    for pagina in range(max_paginas):
        data = http.get(f"{UEFA_API}/matches?competitionId={comp}&fromDate={d1}&toDate={d2}&limit=100"
                        f"&offset={pagina * 100}&order=DESC&seasonYear={temporada}")
        filas = data if isinstance(data, list) else []
        propios += [m for m in filas
                    if str(team_id) in (str((m.get("homeTeam") or {}).get("id")), str((m.get("awayTeam") or {}).get("id")))
                    and _antes_de(m, hasta)]
        if len(propios) >= max_partidos or len(filas) < 100:
            break
    out: dict[str, dict] = {}
    for m in propios[:max_partidos]:
        try:
            lu = http.get(f"{UEFA_API}/matches/{m.get('id')}/lineups")
        except RuntimeError:
            continue  # partido sin alineación publicada todavía
        for lado in ("homeTeam", "awayTeam"):
            t = lu.get(lado) or {}
            if str((t.get("team") or {}).get("id")) != str(team_id):
                continue
            for x in (t.get("field") or []) + (t.get("bench") or []):
                p = x.get("player") or {}
                if p.get("id") is None:
                    continue
                out.setdefault(str(p["id"]), {"id": str(p["id"]), "nombre": p.get("internationalName") or "",
                                              "nombres": [n for n in (p.get("internationalName"),) if n],
                                              "posicion": p.get("fieldPosition") or "",
                                              "jersey": str(x.get("jerseyNumber") or p.get("clubJerseyNumber") or "")})
    return list(out.values())


# ── orquestación ─────────────────────────────────────────────────────────────

def buscar_ids(http: Http, liga: str, sujeto: dict, fecha: datetime | None = None) -> tuple[dict, list[str], list[str]]:
    """Completa `ids` y `posicion` del sujeto (jugador, equipo, rival y alcance
    escritos a mano). Devuelve (sujeto normalizado, errores, avisos); con errores
    el sujeto no debe guardarse. Un id ya escrito que no coincide con el hallado
    es error (no se pisa en silencio)."""
    base = dict(sujeto or {})
    jugador, nombre_equipo = base.get("jugador"), base.get("equipo")
    if liga not in LIGAS:
        return base, [f"la liga '{liga}' no tiene fuentes automáticas"], []
    if not isinstance(jugador, str) or not jugador.strip() or not isinstance(nombre_equipo, str) or not nombre_equipo.strip():
        return base, ["el sujeto necesita 'jugador' y 'equipo' escritos a mano (además de 'rival' y 'alcance')"], []
    errores: list[str] = []
    avisos: list[str] = []
    hallados: dict[str, dict] = {}
    fecha = fecha or datetime.now(timezone.utc)

    try:
        eq, nota = equipo_unico(equipos_espn(http, liga), nombre_equipo)
        if eq is None:
            return base, [f"ESPN: {nota}"], avisos
        j, nota = candidato_unico(plantel_espn(http, liga, eq), jugador, "espn")
        if j is None:
            errores.append(f"ESPN ({eq['nombre']}): {nota}")
        else:
            hallados["espn"] = j
    except _ERRORES_RED as e:
        return base, [f"ESPN no respondió o cambió de formato: {e}"], avisos

    if deporte(liga) == "nfl":
        try:
            j, nota = candidato_unico(plantel_cbs(http, eq["abbr"]), jugador, "cbs")
            if j is None:
                errores.append(f"CBS ({CBS_ABBR.get(eq['abbr'], eq['abbr'])}): {nota}")
            else:
                hallados["cbs"] = j
        except _ERRORES_RED as e:
            errores.append(f"CBS no respondió o cambió de formato: {e}")
    elif liga in UEFA_COMPETICION:
        temporada = temporada_uefa(fecha)
        try:
            eq_u, nota = equipo_unico(equipos_uefa(http, liga, temporada), nombre_equipo)
            if eq_u is None:
                errores.append(f"UEFA: {nota}")
            else:
                plantel = plantel_uefa(http, liga, eq_u["id"], temporada)
                if not candidatos_exactos(plantel, jugador, "uefa"):
                    respaldo = plantel_uefa_alineaciones(http, liga, eq_u["id"], temporada, fecha - timedelta(hours=3))
                    if candidatos_exactos(respaldo, jugador, "uefa"):
                        avisos.append(f"UEFA: {jugador} no aparece en compstats; id tomado de alineaciones previas de {eq_u['nombre']}")
                        plantel = respaldo
                j, nota = candidato_unico(plantel, jugador, "uefa")
                if j is None:
                    errores.append(f"UEFA ({eq_u['nombre']}): {nota}")
                else:
                    hallados["uefa"] = j
        except _ERRORES_RED as e:
            errores.append(f"UEFA no respondió o cambió de formato: {e}")

    j_espn = hallados.get("espn")
    if j_espn:
        for fuente, clave in (("CBS", "cbs"), ("UEFA", "uefa")):
            if clave in hallados:
                e_, a_ = cruzar(j_espn, hallados[clave], fuente, con_posicion=deporte(liga) == "nfl")
                errores += e_
                avisos += a_

    ids = {str(k): str(v).strip() for k, v in (base.get("ids") or {}).items() if v not in (None, "")} \
        if isinstance(base.get("ids"), dict) else {}
    for clave, j in hallados.items():
        if ids.get(clave) and ids[clave] != j["id"]:
            errores.append(f"ids.{clave} ya dice {ids[clave]} pero la búsqueda da {j['id']} ({j.get('nombre')}): verificar a mano")
        ids[clave] = j["id"]
    faltan = sorted(IDS_REQUERIDOS(liga) - set(ids))
    if faltan and not errores:
        errores.append(f"sin ids obligatorios: {', '.join(faltan)}")

    posicion = base.get("posicion")
    if j_espn:
        pos_espn = str(j_espn.get("posicion") or "").strip().upper()
        if isinstance(posicion, str) and posicion.strip() and pos_espn \
                and _pos_nfl(posicion) != _pos_nfl(pos_espn):
            if deporte(liga) == "nfl" and _grupo_pos_nfl(posicion) == _grupo_pos_nfl(pos_espn):
                avisos.append(f"sujeto.posicion '{posicion}' y ESPN '{pos_espn}': mismo grupo {_grupo_pos_nfl(pos_espn)}")
            else:
                errores.append(f"sujeto.posicion '{posicion}' ≠ posición en ESPN '{pos_espn}'")
        posicion = posicion if isinstance(posicion, str) and posicion.strip() else pos_espn

    return normalizar_sujeto({**base, "posicion": posicion, "ids": ids}), errores, avisos
