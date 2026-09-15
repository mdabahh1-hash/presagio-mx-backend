"""Emparejar mercados con partidos y derivar el veredicto. Funciones puras (sin red)
para poder testearlas.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from .fuentes import (AET, CANCELLED, CBS_ABBR, FT, LIVE, NFL_CATEGORIAS_OFENSIVAS, POSTPONED, SCHEDULED,
                      UEFA_COMPETICION, Partido)

# Tokens que no distinguen a un club (siglas de forma jurídica, artículos).
_STOP = {
    "fc", "cf", "sc", "cd", "ac", "afc", "ssc", "us", "as", "ss", "fk", "sk", "sv", "vfb", "vfl",
    "tsg", "bsc", "rb", "cp", "club", "de", "del", "da", "do", "la", "el", "the", "al", "1", "07", "04",
    "05", "1899", "1846", "1860", "09",
}
# Prefijos genéricos que comparten clubes distintos de la misma ciudad: si dos
# nombres traen genéricos DISTINTOS (Real Madrid / Atlético Madrid) no son el
# mismo club aunque el resto coincida.
_GENERICOS = {"real", "atletico", "athletic", "sporting", "deportivo", "union", "dinamo", "dynamo",
              "racing", "inter", "lokomotiv", "spartak", "cska"}
_ALIAS = {
    # exónimos en español usados en las preguntas → nombre habitual en ESPN/TSDB
    "colonia": "koln", "cologne": "koln", "munich": "munchen", "turin": "torino",
    "napoles": "napoli", "milan": "milan", "internazionale": "inter", "inter": "inter",
    "psg": "paris saint germain", "man utd": "manchester united", "man city": "manchester city",
    "gladbach": "monchengladbach", "leverkusen": "leverkusen",
    "praha": "prague",  # Slavia/Sparta Praha (pregunta) → Slavia/Sparta Prague (ESPN)
}


def sin_acentos(s: str) -> str:
    s = s.replace("ß", "ss")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalizar(nombre: str) -> str:
    s = sin_acentos(nombre or "").lower()
    s = re.sub(r"(?<=\w)\.(?=\w)", "", s)  # D.C. United → dc united
    s = re.sub(r"[^\w\s]", " ", s)  # puntos, guiones, &, emoji…
    s = re.sub(r"\s+", " ", s).strip()
    for k, v in _ALIAS.items():
        s = re.sub(rf"\b{re.escape(k)}\b", v, s)
    return s


def _tokens(nombre: str) -> set[str]:
    toks = [t for t in normalizar(nombre).split()]
    utiles = {t for t in toks if t not in _STOP}
    return utiles or set(toks)


def similitud(a: str, b: str) -> float:
    """0..1. 1 = mismo club; ≥0.6 se considera cruce válido."""
    na, nb = normalizar(a), normalizar(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = _tokens(a), _tokens(b)
    ga, gb = ta & _GENERICOS, tb & _GENERICOS
    if ga and gb and ga != gb:
        return 0.4  # Real Madrid ≠ Atlético Madrid
    if ta == tb:
        return 1.0
    if ta <= tb or tb <= ta:
        return 0.9
    inter = ta & tb
    jaccard = len(inter) / len(ta | tb)
    # prefijo largo (inter ↔ internazionale, famalicao ↔ fc famalicao)
    # solo entre los tokens que difieren: un token idéntico compartido
    # (manchester city / manchester united) no cuenta como prefijo.
    prefijo = any(
        len(x) >= 4 and (y.startswith(x) or x.startswith(y)) for x in ta - tb for y in tb - ta
    )
    # la similitud de cadena solo rescata erratas, no clubes de la misma ciudad
    # (manchester city / manchester united = 0.73)
    secuencia = SequenceMatcher(None, na, nb).ratio()
    return max(jaccard, 0.8 if prefijo else 0.0, secuencia if secuencia >= 0.85 else 0.0)


# ── parsear el mercado ───────────────────────────────────────────────────────

_RE_QUIEN_GANA = re.compile(r"¿\s*qui[eé]n gana(?:r[aá])?\s+(.+?)\s+vs\.?\s+(.+?)\s*\?", re.I)
_RE_X_VS_Y_QUIEN = re.compile(r"^\s*(.+?)\s+vs\.?\s+(.+?)\s+[—-]+\s*¿qui[eé]n gana", re.I)
_RE_TITULAR = re.compile(
    r"¿\s*(?P<jugador>.+?)\s+ser[aá] titular\s+(?:en|con)\s+(?P<resto>.+?)\s*\?", re.I
)
_RE_GOL = re.compile(r"¿\s*(?P<jugador>.+?)\s+(?:anota|marca|mete)\b.*?\b(?:en|ante|contra|vs\.?)\s+(?P<resto>.+?)\s*\?", re.I)


def _quitar_emoji(label: str) -> str:
    return re.sub(r"^[^\w¿¡]+", "", label or "").strip()


def equipos_partido(mercado: dict) -> tuple[str, str] | None:
    """(local, visitante) de un 1X2. Prefiere las etiquetas de los outcomes
    (🏠 X / ✈️ Y), luego la pregunta."""
    labels = {o.get("outcome_key"): _quitar_emoji(o.get("label", "")) for o in mercado.get("outcomes") or []}
    if labels.get("local") and labels.get("visitante"):
        return labels["local"], labels["visitante"]
    q = mercado.get("question") or ""
    m = _RE_QUIEN_GANA.search(q) or _RE_X_VS_Y_QUIEN.search(q)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


def _equipos_de_resto(resto: str) -> list[str]:
    """'Crystal Palace vs Manchester City' → 2 equipos; 'Manchester City ante Porto en la Jornada 1…' → 2."""
    resto = re.sub(r"\s+en la jornada.*$", "", resto, flags=re.I)
    resto = re.sub(r"\s+\(.*\)$", "", resto)
    partes = re.split(r"\s+(?:vs\.?|ante|contra|frente a)\s+", resto, flags=re.I)
    return [p.strip() for p in partes if p.strip()][:2]


def parse_titular(mercado: dict) -> dict | None:
    m = _RE_TITULAR.search(mercado.get("question") or "")
    if not m:
        return None
    equipos = _equipos_de_resto(m.group("resto"))
    if not equipos:
        return None
    return {"jugador": m.group("jugador").strip(), "equipos": equipos}


_RE_GOL_JUGADOR = re.compile(r"¿\s*(?P<jugador>[^¿?]+?)\s+(?:anota|anotar[aá]|marca|marcar[aá]|mete|meter[aá])\b", re.I)


def parse_gol(mercado: dict) -> dict | None:
    """'¿X anota gol ante Y…?' → equipos [Y]; '¿X marcará al menos un gol en su
    primer partido de la Champions?' → equipos [] (se localiza por alineación)."""
    q = mercado.get("question") or ""
    if "gol" not in q.lower():
        return None
    m = _RE_GOL_JUGADOR.search(q)
    if not m:
        return None
    jugador = m.group("jugador").strip()
    equipos: list[str] = []
    m2 = re.search(r"\b(?:ante|contra|frente a|vs\.?)\s+(.+?)\s*(?:\?|\ben la jornada\b)", q, re.I)
    if m2:
        equipos = _equipos_de_resto(m2.group(1))
    return {"jugador": jugador, "equipos": equipos}


# ── emparejar ────────────────────────────────────────────────────────────────

UMBRAL = 0.6


def _score_lado(nombre: str, partido: Partido, lado: str) -> float:
    candidatos = [partido.home if lado == "home" else partido.away]
    if partido.alias:
        sep = partido.alias.index("|") if "|" in partido.alias else len(partido.alias)
        candidatos += partido.alias[:sep] if lado == "home" else partido.alias[sep + 1:]
    return max(similitud(nombre, c) for c in candidatos if c)


def emparejar(local: str, visitante: str, kickoff: datetime, partidos: list[Partido],
              tolerancia_h: float = 6) -> tuple[Partido | None, str]:
    """Busca el partido de `local vs visitante` cerca del kickoff. Devuelve
    (partido, nota); partido=None si no hay cruce claro. Detecta sede invertida."""
    ventana = [p for p in partidos if abs((p.kickoff - kickoff).total_seconds()) <= tolerancia_h * 3600]
    if not ventana:
        return None, "ningún partido de la liga cerca de la hora de cierre"
    puntuados = []
    for p in ventana:
        directo = min(_score_lado(local, p, "home"), _score_lado(visitante, p, "away"))
        invertido = min(_score_lado(local, p, "away"), _score_lado(visitante, p, "home"))
        puntuados.append((directo, invertido, p))
    puntuados.sort(key=lambda t: max(t[0], t[1]), reverse=True)
    directo, invertido, mejor = puntuados[0]
    if max(directo, invertido) < UMBRAL:
        return None, f"sin cruce claro (mejor candidato: {mejor.home} vs {mejor.away}, similitud {max(directo, invertido):.2f})"
    if len(puntuados) > 1:
        segundo = max(puntuados[1][0], puntuados[1][1])
        if segundo >= UMBRAL and abs(segundo - max(directo, invertido)) < 0.15:
            return None, f"cruce ambiguo entre {mejor.home} vs {mejor.away} y {puntuados[1][2].home} vs {puntuados[1][2].away}"
    if invertido > directo:
        return None, f"sede invertida: la fuente registra {mejor.home} (local) vs {mejor.away}; el mercado dice {local} local"
    return mejor, ""


# ── veredicto ────────────────────────────────────────────────────────────────

def veredicto_1x2(p: Partido) -> tuple[str | None, str]:
    """('local'|'empate'|'visitante', '') o (None, razón)."""
    if p.estado == POSTPONED:
        return None, "partido aplazado"
    if p.estado == CANCELLED:
        return None, "partido cancelado o abandonado"
    if p.estado in (SCHEDULED, LIVE):
        return None, f"partido no terminado ({p.estado})"
    if p.estado == AET:
        return None, "definido en prórroga/penales: revisar normas (cuenta el minuto 90)"
    if p.estado != FT or p.home_score is None or p.away_score is None:
        return None, f"estado {p.estado} sin marcador final"
    if p.home_score > p.away_score:
        return "local", ""
    if p.home_score < p.away_score:
        return "visitante", ""
    return "empate", ""


def fecha_corta(dt: datetime) -> str:
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{dt.day:02d}-{meses[dt.month - 1]}-{dt.year}"


def resolver_1x2(mercado: dict, espn: Partido | None, nota_espn: str,
                 tsdb: Partido | None) -> dict:
    """Combina ambas fuentes. Devuelve una entrada de plan (confianza alta) o un
    escalado con la evidencia disponible."""
    base = {"id": mercado["id"], "pregunta": mercado.get("question"), "liga": mercado.get("subcategory"),
            "volume": round(float(mercado.get("volume") or 0)), "num_trades": int(mercado.get("num_trades") or 0)}
    if espn is None:
        return {**base, "escalar": True, "razon": f"ESPN: {nota_espn}"}
    v1, r1 = veredicto_1x2(espn)
    if v1 is None:
        return {**base, "escalar": True, "razon": f"ESPN: {r1}", "resultado": espn.marcador, "fuente_1": espn.url}
    resultado = f"{espn.home} {espn.home_score}-{espn.away_score} {espn.away} ({fecha_corta(espn.kickoff)})"
    if tsdb is None:
        return {**base, "escalar": True, "razon": "solo una fuente (TheSportsDB no encontró el partido)",
                "veredicto_sugerido": v1, "resultado": resultado, "fuente_1": espn.url}
    v2, r2 = veredicto_1x2(tsdb)
    if v2 is None:
        return {**base, "escalar": True, "razon": f"TheSportsDB: {r2}", "veredicto_sugerido": v1,
                "resultado": resultado, "fuente_1": espn.url, "fuente_2": tsdb.url}
    if (espn.home_score, espn.away_score) != (tsdb.home_score, tsdb.away_score):
        return {**base, "escalar": True,
                "razon": f"las fuentes discrepan: ESPN {espn.home_score}-{espn.away_score}, TheSportsDB {tsdb.home_score}-{tsdb.away_score}",
                "resultado": resultado, "fuente_1": espn.url, "fuente_2": tsdb.url}
    return {**base, "veredicto": v1, "resultado": resultado, "fuente_1": espn.url, "fuente_2": tsdb.url,
            "confianza": "alta"}


# ── NFL: ganador por equipo (outcomes con key de equipo, sede irrelevante) ──

def _quitar_parentesis(q: str) -> str:
    return re.sub(r"\s*\(.*?\)\s*", " ", q).strip()


def equipos_ganador(mercado: dict) -> list[tuple[str, str]] | None:
    """[(outcome_key, nombre de equipo)] de un mercado '¿Quién gana A vs B?'
    cuyos outcomes son los equipos (NFL: `seahawks`/`patriots`). Usa las
    etiquetas de los outcomes (sin emoji); None si no hay exactamente dos."""
    outs = [(o.get("outcome_key"), _quitar_emoji(o.get("label", ""))) for o in mercado.get("outcomes") or []]
    outs = [(k, n) for k, n in outs if k and n]
    if len(outs) != 2 or {k for k, _ in outs} & {"local", "empate", "visitante"}:
        return None
    return outs


def emparejar_cualquier_sede(nombres: list[str], kickoff: datetime, partidos: list[Partido],
                             tolerancia_h: float = 6) -> tuple[Partido | None, str]:
    """Partido cercano al kickoff donde juegan ambos equipos, en cualquier
    orientación (la NFL juega en sede neutral y las preguntas no fijan local)."""
    ventana = [p for p in partidos if abs((p.kickoff - kickoff).total_seconds()) <= tolerancia_h * 3600]
    if not ventana:
        return None, "ningún partido de la liga cerca de la hora de cierre"
    puntuados = []
    for p in ventana:
        a, b = nombres
        directo = min(_score_lado(a, p, "home"), _score_lado(b, p, "away"))
        invertido = min(_score_lado(a, p, "away"), _score_lado(b, p, "home"))
        puntuados.append((max(directo, invertido), p))
    puntuados.sort(key=lambda t: t[0], reverse=True)
    score, mejor = puntuados[0]
    if score < UMBRAL:
        return None, f"sin cruce claro (mejor candidato: {mejor.home} vs {mejor.away}, similitud {score:.2f})"
    if len(puntuados) > 1 and puntuados[1][0] >= UMBRAL and abs(puntuados[1][0] - score) < 0.15:
        return None, f"cruce ambiguo entre {mejor.home} vs {mejor.away} y {puntuados[1][1].home} vs {puntuados[1][1].away}"
    return mejor, ""


def ganador(p: Partido) -> tuple[str | None, str]:
    """(nombre del equipo ganador, '') o (None, razón). Empate → razón 'empate'
    (en NFL el mercado se cancela por normas)."""
    if p.estado == POSTPONED:
        return None, "partido aplazado"
    if p.estado == CANCELLED:
        return None, "partido cancelado o abandonado"
    if p.estado in (SCHEDULED, LIVE):
        return None, f"partido no terminado ({p.estado})"
    if p.estado not in (FT, AET) or p.home_score is None or p.away_score is None:
        return None, f"estado {p.estado} sin marcador final"
    if p.home_score == p.away_score:
        return None, "empate"
    return (p.home if p.home_score > p.away_score else p.away), ""


def _key_de_equipo(nombre: str, outs: list[tuple[str, str]]) -> str | None:
    puntuados = sorted(((similitud(nombre, n), k) for k, n in outs), reverse=True)
    if puntuados[0][0] < UMBRAL or (len(puntuados) > 1 and puntuados[0][0] - puntuados[1][0] < 0.15):
        return None
    return puntuados[0][1]


def resolver_ganador(mercado: dict, outs: list[tuple[str, str]], espn: Partido | None, nota_espn: str,
                     tsdb: Partido | None) -> dict:
    """Como resolver_1x2 pero el veredicto es el outcome_key del equipo ganador.
    Empate confirmado en ambas fuentes → escalado con sugerencia CANCELAR."""
    base = {"id": mercado["id"], "pregunta": mercado.get("question"), "liga": mercado.get("subcategory"),
            "volume": round(float(mercado.get("volume") or 0)), "num_trades": int(mercado.get("num_trades") or 0)}
    if espn is None:
        return {**base, "escalar": True, "razon": f"ESPN: {nota_espn}"}
    g1, r1 = ganador(espn)
    resultado = f"{espn.home} {espn.home_score}-{espn.away_score} {espn.away} ({fecha_corta(espn.kickoff)})" \
        if espn.home_score is not None else espn.marcador
    if g1 is None and r1 != "empate":
        return {**base, "escalar": True, "razon": f"ESPN: {r1}", "resultado": resultado, "fuente_1": espn.url}
    key = _key_de_equipo(g1, outs) if g1 else "CANCELAR"
    if key is None:
        return {**base, "escalar": True, "razon": f"no pude mapear al ganador '{g1}' a un outcome", "resultado": resultado, "fuente_1": espn.url}
    if tsdb is None:
        return {**base, "escalar": True, "razon": "solo una fuente (TheSportsDB no encontró el partido)",
                "veredicto_sugerido": key, "resultado": resultado, "fuente_1": espn.url}
    g2, r2 = ganador(tsdb)
    if g2 is None and r2 != "empate":
        return {**base, "escalar": True, "razon": f"TheSportsDB: {r2}", "veredicto_sugerido": key,
                "resultado": resultado, "fuente_1": espn.url, "fuente_2": tsdb.url}
    if (espn.home_score, espn.away_score) != (tsdb.home_score, tsdb.away_score) and \
            (espn.home, espn.home_score, espn.away_score) != (tsdb.away, tsdb.away_score, tsdb.home_score):
        return {**base, "escalar": True,
                "razon": f"las fuentes discrepan: ESPN {espn.home_score}-{espn.away_score}, TheSportsDB {tsdb.home_score}-{tsdb.away_score}",
                "resultado": resultado, "fuente_1": espn.url, "fuente_2": tsdb.url}
    if key == "CANCELAR":
        return {**base, "escalar": True, "razon": "empate oficial en ambas fuentes: por normas el mercado se cancela",
                "veredicto_sugerido": "CANCELAR", "resultado": resultado, "fuente_1": espn.url, "fuente_2": tsdb.url}
    return {**base, "veredicto": key, "resultado": f"{resultado}: gana {g1}", "fuente_1": espn.url, "fuente_2": tsdb.url,
            "confianza": "alta"}


# ── NFL: props de jugador (ESPN + CBS, jugador por id del sujeto) ────────────
#
# El partido sale de `sujeto.equipo` + `rival` (plan._plan_nfl) y el jugador se
# ubica por `sujeto.ids` en cada box score, nunca por nombre. Estados por
# fuente: ok | ausente | otro_equipo | discrepa | sin_id | caida. Reglas de
# sugerencia en resolver_prop_nfl.

_RE_PROP_TD = re.compile(r"¿\s*(?P<jugador>.+?)\s+anotar[aá] al menos (?P<n>\d+) touchdown", re.I)
_RE_PROP_PASES = re.compile(r"¿\s*(?P<jugador>.+?)\s+lanzar[aá] (?P<n>\d+) o m[aá]s pases de touchdown", re.I)
_RE_PROP_FANTASY = re.compile(r"¿\s*(?P<jugador>.+?)\s+conseguir[aá] (?P<n>\d+(?:[.,]\d+)?) o m[aá]s puntos de fantasy", re.I)


def parse_prop_nfl(mercado: dict) -> dict | None:
    """{'jugador', 'tipo': 'td'|'pases_td'|'fantasy', 'umbral'} o None."""
    q = mercado.get("question") or ""
    for tipo, rx in (("td", _RE_PROP_TD), ("pases_td", _RE_PROP_PASES), ("fantasy", _RE_PROP_FANTASY)):
        m = rx.search(q)
        if m:
            return {"jugador": m.group("jugador").strip(), "tipo": tipo, "umbral": float(m.group("n").replace(",", "."))}
    return None


def _num(stats: dict | None, key: str) -> float:
    try:
        return float(str((stats or {}).get(key, 0) or 0).split("/")[0])
    except ValueError:
        return 0.0


def fantasy_estandar(j: dict) -> tuple[float, str]:
    """Puntos de fantasy con el scoring estándar de ESPN (sin PPR): 0.04/yd de
    pase, 4/TD de pase, −2/INT, 0.1/yd de carrera o recepción, 6/TD de carrera o
    recepción, −2/fumble perdido. Las conversiones de 2 puntos no vienen en el
    box score (se avisa en el detalle)."""
    p, r, c, f = j.get("passing"), j.get("rushing"), j.get("receiving"), j.get("fumbles")
    pts = (0.04 * _num(p, "passingYards") + 4 * _num(p, "passingTouchdowns") - 2 * _num(p, "interceptions")
           + 0.1 * (_num(r, "rushingYards") + _num(c, "receivingYards"))
           + 6 * (_num(r, "rushingTouchdowns") + _num(c, "receivingTouchdowns"))
           - 2 * _num(f, "fumblesLost"))
    detalle = (f"pase {_num(p, 'passingYards'):.0f} yd/{_num(p, 'passingTouchdowns'):.0f} TD/{_num(p, 'interceptions'):.0f} INT · "
               f"carrera {_num(r, 'rushingYards'):.0f} yd/{_num(r, 'rushingTouchdowns'):.0f} TD · "
               f"recepción {_num(c, 'receivingYards'):.0f} yd/{_num(c, 'receivingTouchdowns'):.0f} TD · "
               f"fumbles perdidos {_num(f, 'fumblesLost'):.0f} (sin contar conversiones de 2 pts)")
    return round(pts, 2), detalle


def abbrs_partido(p: Partido) -> tuple[str | None, str | None]:
    """(abreviatura local, abreviatura visitante) del alias de ESPN
    (displayName, shortDisplayName, name, abbreviation | …)."""
    sep = p.alias.index("|") if "|" in p.alias else len(p.alias)

    def abbr(lado: list[str]) -> str | None:
        cands = [x for x in lado if x and re.fullmatch(r"[A-Z0-9]{2,4}", x)]
        return cands[-1] if cands else None

    return abbr(p.alias[:sep]), abbr(p.alias[sep + 1:])


def lado_del_equipo(p: Partido, equipo: str) -> dict | None:
    """Lado del partido donde juega `equipo`: {lado: home|away, nombre, abbr,
    rival, rival_abbr}. None si no llega a UMBRAL o si los dos lados quedan a
    menos de 0.15 (ambiguo)."""
    sh, sa = _score_lado(equipo, p, "home"), _score_lado(equipo, p, "away")
    if max(sh, sa) < UMBRAL or abs(sh - sa) < 0.15:
        return None
    ah, aa = abbrs_partido(p)
    if sh > sa:
        return {"lado": "home", "nombre": p.home, "abbr": ah, "rival": p.away, "rival_abbr": aa}
    return {"lado": "away", "nombre": p.away, "abbr": aa, "rival": p.home, "rival_abbr": ah}


_FUENTE_NOMBRE = {"espn": "ESPN", "cbs": "CBS", "uefa": "UEFA", "tsdb": "TheSportsDB"}


def _abbr_igual(a: str | None, b: str | None) -> bool:
    """Misma abreviatura de equipo entre ESPN y CBS (JAX = JAC, WSH = WAS)."""
    return bool(a) and bool(b) and CBS_ABBR.get(a, a) == CBS_ABBR.get(b, b)


def _nombre_identico(a: str, b: str) -> bool:
    """Nombre normalizado idéntico, o igual sin espacios (el slug de CBS da
    'dandre swift' para D'Andre Swift). Nunca subconjuntos."""
    na, nb = normalizar(a), normalizar(b)
    return bool(na) and (na == nb or na.replace(" ", "") == nb.replace(" ", ""))


def localizar_jugador(bs: dict | None, sujeto: dict, fuente: str, abbr: str) -> dict:
    """Ubica al jugador del sujeto en un box score (`espn_boxscore_nfl` o
    `parsear_cbs_boxscore`, ambos indexados por id) SOLO por `sujeto.ids[fuente]`.
    `abbr` es la abreviatura ESPN del equipo del sujeto en el partido elegido.
    Devuelve {fuente, estado, id, nombre, abbr, nota}:
    - caida: la fuente no respondió;  sin_id: el sujeto no trae id de la fuente;
    - ok: la fila del id es del mismo jugador (`_persona_coincide` o nombre
      idéntico) y del equipo (o equipo no publicado, abbr '?');
    - discrepa: la fila del id es de otra persona, o el id no está pero sí un
      jugador del equipo con el nombre idéntico (id equivocado);
    - otro_equipo: la fila del id es de otro equipo (traspaso, sujeto mal);
    - ausente: el id no aparece (el box score no publica inactivos)."""
    nombre_f = _FUENTE_NOMBRE.get(fuente, fuente)
    jugador = str(sujeto.get("jugador") or "")
    pid = str((sujeto.get("ids") or {}).get(fuente) or "").strip()
    base = {"fuente": fuente, "id": pid or None, "nombre": None, "abbr": None}
    if bs is None:
        return {**base, "estado": "caida", "nota": f"{nombre_f} no respondió (sin box score)"}
    if not pid:
        return {**base, "estado": "sin_id", "nota": f"el sujeto no trae ids.{fuente}: no se localiza por nombre"}
    filas = bs.get("jugadores") or {}
    fila = filas.get(pid)
    if fila is not None:
        nombre, abbr_fila = str(fila.get("nombre") or ""), str(fila.get("abbr") or "?")
        out = {**base, "nombre": nombre, "abbr": abbr_fila}
        if not (_persona_coincide(jugador, nombre) or _nombre_identico(jugador, nombre)):
            return {**out, "estado": "discrepa",
                    "nota": f"el id {pid} es {nombre} ({abbr_fila}) en {nombre_f}, no {jugador}"}
        if abbr_fila != "?" and not _abbr_igual(abbr_fila, abbr):
            return {**out, "estado": "otro_equipo",
                    "nota": f"{nombre} (id {pid}) aparece con {abbr_fila} en {nombre_f}, no con {abbr}"}
        equipo_txt = abbr_fila if abbr_fila != "?" else f"equipo no publicado; partido de {abbr}"
        return {**out, "estado": "ok", "nota": f"{nombre} (id {pid}, {equipo_txt})"}
    mismos = [f for f in filas.values()
              if (str(f.get("abbr") or "?") == "?" or _abbr_igual(f.get("abbr"), abbr))
              and _nombre_identico(jugador, str(f.get("nombre") or ""))]
    if mismos:
        otros = ", ".join(f"id {f.get('id') or '?'}" for f in mismos)
        return {**base, "estado": "discrepa",
                "nota": f"el id {pid} no está en el box score de {nombre_f}, pero sí un {mismos[0].get('nombre')} "
                        f"de {abbr} con otro id ({otros}): ¿id equivocado?"}
    nota = f"{jugador} (id {pid}) no aparece en el box score de {nombre_f}"
    lesion = next((i for i in (bs.get("injuries") or {}).get(abbr, []) if i.get("id") == pid), None)
    if lesion:
        nota += f"; reporte de lesiones de ESPN: {lesion.get('estado')}"
    return {**base, "estado": "ausente", "nota": nota}


def tabla_ofensiva(spec: dict, jugador_stats: dict) -> bool:
    """¿Trae el jugador la tabla de la que sale la prop? pases_td → passing;
    td → rushing o receiving; fantasy → alguna ofensiva. Un jugador presente
    solo en defensa o devoluciones no la trae."""
    if spec["tipo"] == "pases_td":
        return bool(jugador_stats.get("passing"))
    if spec["tipo"] == "td":
        return bool(jugador_stats.get("rushing") or jugador_stats.get("receiving"))
    return any(jugador_stats.get(c) for c in NFL_CATEGORIAS_OFENSIVAS)


def sugerir_prop_nfl(spec: dict, jugador_stats: dict) -> tuple[str | None, str]:
    """('YES'|'NO'|None, detalle) a partir del box score del jugador (ya
    localizado por id). Sin la tabla ofensiva (jugó solo en defensa o
    devoluciones): pases_td y fantasy → NO, que resolver_prop_nfl nunca da como
    alta; td → None (sin jugada ofensiva registrada, podría ser CANCELAR)."""
    if not tabla_ofensiva(spec, jugador_stats):
        if spec["tipo"] == "td":
            return None, "sin tabla de carrera ni de recepción: presente en el partido pero sin jugada ofensiva registrada"
        if spec["tipo"] == "pases_td":
            return "NO", f"sin tabla de pase: presente en el partido pero sin pases registrados (umbral {spec['umbral']:.0f})"
        return "NO", f"sin tablas ofensivas: presente en el partido pero sin yardas ni touchdowns (umbral {spec['umbral']:.1f})"
    r, c, p = jugador_stats.get("rushing"), jugador_stats.get("receiving"), jugador_stats.get("passing")
    if spec["tipo"] == "td":
        n = _num(r, "rushingTouchdowns") + _num(c, "receivingTouchdowns")
        return ("YES" if n >= spec["umbral"] else "NO"), f"{n:.0f} TD por carrera/recepción (umbral {spec['umbral']:.0f})"
    if spec["tipo"] == "pases_td":
        n = _num(p, "passingTouchdowns")
        return ("YES" if n >= spec["umbral"] else "NO"), f"{n:.0f} pases de TD (umbral {spec['umbral']:.0f})"
    pts, detalle = fantasy_estandar(jugador_stats)
    return ("YES" if pts >= spec["umbral"] else "NO"), f"{pts:.2f} pts fantasy estándar (umbral {spec['umbral']:.1f}): {detalle}"


# ── nombre de persona: SOLO chequeo de cordura junto a un id ─────────────────

def _persona_coincide(a: str, b: str) -> bool:
    """Mismo jugador: nombres iguales, uno contenido en el otro (Cherki ⊂ Rayan
    Cherki) o mismo apellido final con nombre compatible. Compartir solo el
    nombre de pila (Federico Dimarco / Federico Valverde) NO es coincidencia."""
    na, nb = normalizar(a), normalizar(b)
    if na == nb:
        return True
    ta, tb = na.split(), nb.split()
    if not ta or not tb:
        return False
    if set(ta) <= set(tb) or set(tb) <= set(ta):
        return True
    if ta[-1] != tb[-1]:
        return False
    # mismo apellido pero nombre de pila distinto (Kylian Mbappé / Ethan Mbappé)
    if len(ta) >= 2 and len(tb) >= 2 and ta[0] != tb[0] \
            and not (ta[0].startswith(tb[0]) or tb[0].startswith(ta[0])):
        return False
    return SequenceMatcher(None, na, nb).ratio() >= 0.6


# Fantasy NO a este margen del umbral o menos se escala: las conversiones de 2
# puntos (+2 cada una) cuentan en las normas pero no vienen en el box score.
MARGEN_FANTASY_NO = 4.0
# Estados de localización que impiden cualquier sugerencia (D1).
_SIN_IDENTIDAD = ("otro_equipo", "discrepa", "sin_id", "caida", "ambiguo")


def resolver_prop_nfl(mercado: dict, spec: dict, sujeto: dict, partido: Partido, lado: dict,
                      espn: dict | None, cbs: dict | None, loc_e: dict | None, loc_c: dict | None) -> dict:
    """Prop de NFL con dos box scores (ESPN + CBS). `partido` y `lado`
    (lado_del_equipo) salen de `sujeto.equipo` + `rival`; `loc_e`/`loc_c` de
    localizar_jugador. Primero se calculan las dos notas y luego:
    - otro_equipo / discrepa / sin_id / caida en cualquier fuente → escalado SIN
      sugerencia (la razón lleva las notas de ambas);
    - ok en una y ausente en la otra → escalado SIN sugerencia;
    - ausente en ambas → escalado con sugerencia CANCELAR, nunca alta (el box
      score no publica inactivos: confirmar que no jugó);
    - ok en ambas: fantasy con fumble perdido (CBS no publica fumbles) →
      escalado con la sugerencia de ESPN; veredictos distintos → escalado con
      la de ESPN; sin tabla ofensiva (td) → sin sugerencia, (pases_td/fantasy)
      → sugerencia NO; fantasy NO a ≤ MARGEN_FANTASY_NO del umbral → escalado
      con NO; si no, confianza alta.
    Toda salida lleva `sujeto_confirmado` {jugador, equipo, partido, espn?, cbs?}
    (bloque por fuente solo con estado ok) y la identidad en `resultado`."""
    base = {"id": mercado["id"], "pregunta": mercado.get("question"), "liga": mercado.get("subcategory"),
            "volume": round(float(mercado.get("volume") or 0)), "num_trades": int(mercado.get("num_trades") or 0)}
    marcador = f"{partido.marcador} ({fecha_corta(partido.kickoff)})"
    jugador = sujeto["jugador"]
    loc_e = loc_e or localizar_jugador(espn, sujeto, "espn", lado.get("abbr") or "")
    loc_c = loc_c or localizar_jugador(cbs, sujeto, "cbs", lado.get("abbr") or "")
    notas = f"ESPN: {loc_e['nota']}; CBS: {loc_c['nota']}"

    ah, aa = abbrs_partido(partido)
    confirmado: dict = {"jugador": jugador, "equipo": lado["nombre"],
                        "partido": f"{aa}@{ah}" if ah and aa else f"{partido.away} @ {partido.home}"}
    for loc in (loc_e, loc_c):
        if loc["estado"] == "ok":
            confirmado[loc["fuente"]] = {"id": loc["id"], "nombre": loc["nombre"], "abbr": loc["abbr"],
                                         "equipo": lado["nombre"]}
    partes = [lado.get("abbr") or lado["nombre"]]
    partes += [f"{_FUENTE_NOMBRE[f]} {confirmado[f]['id']}" for f in ("espn", "cbs") if f in confirmado]
    ident = f"{jugador} ({' · '.join(partes)})"
    urls = {"fuente_1": espn["url"] if espn else partido.url}
    if cbs:
        urls["fuente_2"] = cbs["url"]
    esc = {**base, "escalar": True, **urls, "sujeto_confirmado": confirmado}
    ee, ec = loc_e["estado"], loc_c["estado"]

    def detalle(loc: dict, bs: dict | None) -> tuple[str | None, str]:
        return sugerir_prop_nfl(spec, bs["jugadores"][loc["id"]])

    if ee in _SIN_IDENTIDAD or ec in _SIN_IDENTIDAD:
        evidencia = "; ".join(f"{_FUENTE_NOMBRE[loc['fuente']]}: {detalle(loc, bs)[1]}"
                              for loc, bs in ((loc_e, espn), (loc_c, cbs)) if loc["estado"] == "ok")
        return {**esc, "razon": f"identidad no confirmada en las dos fuentes, sin sugerencia ({notas})",
                "resultado": f"{marcador} — {ident}" + (f": {evidencia}" if evidencia else "")}
    if ee == "ausente" and ec == "ausente":
        return {**esc, "veredicto_sugerido": "CANCELAR",
                "razon": (f"partido identificado por equipo ({lado['nombre']}: {partido.marcador}); {jugador} no aparece "
                          f"en el box score de ESPN ni en el de CBS. El box score no publica la lista de inactivos: "
                          f"confirmar que no jugó antes de cancelar ({notas})"),
                "resultado": f"{marcador} — {jugador}: ausente de ambos box scores"}
    if ee != ec:  # ok en una, ausente en la otra
        tiene, falta = ("ESPN", "CBS") if ee == "ok" else ("CBS", "ESPN")
        loc, bs = (loc_e, espn) if ee == "ok" else (loc_c, cbs)
        return {**esc, "razon": f"{jugador} aparece en el box score de {tiene} pero no en el de {falta}, sin sugerencia ({notas})",
                "resultado": f"{marcador} — {ident}: {tiene} {detalle(loc, bs)[1]}"}

    e_stats, c_stats = espn["jugadores"][loc_e["id"]], cbs["jugadores"][loc_c["id"]]
    v1, d1 = sugerir_prop_nfl(spec, e_stats)
    v2, d2 = sugerir_prop_nfl(spec, c_stats)
    resultado = f"{marcador} — {ident}: {d1}; CBS: {d2}"
    sug = {"veredicto_sugerido": v1} if v1 else {}
    if spec["tipo"] == "fantasy" and _num(e_stats.get("fumbles"), "fumblesLost") > 0:
        return {**esc, **sug, "razon": "fantasy con balón suelto perdido según ESPN; CBS no publica fumbles: confirmar a mano",
                "resultado": resultado}
    if v1 != v2:
        return {**esc, **sug, "razon": f"las fuentes discrepan: ESPN {v1} ({d1}) vs CBS {v2} ({d2})", "resultado": resultado}
    if v1 is None:
        return {**esc, "razon": f"ESPN y CBS: {d1}; sin sugerencia (si no tuvo jugada ofensiva, por normas se cancela)",
                "resultado": resultado}
    if not (tabla_ofensiva(spec, e_stats) and tabla_ofensiva(spec, c_stats)):
        return {**esc, **sug, "razon": (f"{jugador} está en el partido pero sin tabla ofensiva en ESPN o CBS: confirmar que "
                                        "jugó (si no participó, por normas se cancela)"),
                "resultado": resultado}
    if spec["tipo"] == "fantasy" and v1 == "NO":
        pts = max(fantasy_estandar(e_stats)[0], fantasy_estandar(c_stats)[0])
        if pts >= spec["umbral"] - MARGEN_FANTASY_NO:
            return {**esc, **sug, "razon": (f"fantasy NO a {spec['umbral'] - pts:.2f} pts del umbral: las conversiones de 2 pts "
                                            "no vienen en el box score: confirmar con ESPN Fantasy"),
                    "resultado": resultado}
    return {**base, "veredicto": v1, "resultado": resultado, **urls, "confianza": "alta", "sujeto_confirmado": confirmado}


# ── fútbol: titular / gol (ESPN + UEFA o TheSportsDB, jugador por id) ─────────
#
# El partido sale de `sujeto.equipo` + `rival` (plan.armar_plan) y el jugador se
# ubica por `sujeto.ids` en las alineaciones de ESPN y de la UEFA, buscando el id
# en LOS DOS equipos para detectar `otro_equipo`. TheSportsDB no trae ids: ahí
# solo cuenta un nombre normalizado idéntico y único dentro del equipo (`ambiguo`
# si se repite) y, como recorta los listados, solo confirma presencias. Mismos
# estados que las props NFL; reglas de sugerencia en resolver_accesorio.

def _nombres_equipo(clave: str, e: dict) -> list[str]:
    return [n for n in [e.get("nombre") or clave, *(e.get("alias") or [])] if n]


def equipo_en_resumen(summary: dict | None, nombres: list[str], equipo_id: str | None = None) -> str | None:
    """Clave de `summary['equipos']` del equipo del sujeto. Con `equipo_id`: el
    único equipo con ese id. Si no: el único con similitud ≥ UMBRAL contra
    `nombres` (sujeto.equipo y el nombre de ESPN del lado) y ventaja ≥ 0.15
    sobre el otro. None si no está o es ambiguo."""
    equipos = (summary or {}).get("equipos") or {}
    if equipo_id not in (None, ""):
        claves = [k for k, e in equipos.items() if str(e.get("id") or "") == str(equipo_id)]
        return claves[0] if len(claves) == 1 else None
    puntuados = sorted(
        ((max((similitud(n, a) for n in nombres if n for a in _nombres_equipo(k, e)), default=0.0), k)
         for k, e in equipos.items()),
        key=lambda t: t[0], reverse=True,
    )
    if not puntuados or puntuados[0][0] < UMBRAL:
        return None
    if len(puntuados) > 1 and puntuados[0][0] - puntuados[1][0] < 0.15:
        return None
    return puntuados[0][1]


def _rol(fila: dict) -> tuple[str, bool | None]:
    """(titular|banca, entró): un titular participa; en la banca, `entro` de la
    fuente (None si no publica cambios)."""
    return ("titular", True) if fila.get("titular") else ("banca", fila.get("entro"))


def _rol_txt(rol: str | None, entro: bool | None) -> str:
    if rol == "titular":
        return "titular"
    if rol == "banca":
        return "banca, entró de cambio" if entro else ("banca, no entró" if entro is False else "banca")
    return "fuera de la alineación, solo en los goles"


def localizar_en_partido(summary: dict | None, sujeto: dict, fuente: str, equipo: str | None) -> dict:
    """Ubica al jugador del sujeto en un resumen de alineaciones (espn_summary,
    uefa_resumen o tsdb_resumen). `equipo` es la clave del equipo del sujeto en
    ese resumen (equipo_en_resumen). ESPN/UEFA: SOLO por `sujeto.ids[fuente]`,
    buscado en los dos equipos; TheSportsDB (sin ids): nombre normalizado
    idéntico dentro del equipo. Devuelve {fuente, estado, id, nombre, equipo,
    rol: titular|banca|None, entro, nota}:
    - caida: sin resumen o sin alineaciones;  sin_id: el sujeto no trae el id;
    - discrepa: el equipo del sujeto no está (o es ambiguo) en el resumen, la
      fila del id es de otra persona, o el id no está pero sí un jugador del
      equipo con el nombre idéntico (¿id equivocado?);
    - otro_equipo: el id (o, en TheSportsDB, el nombre) aparece en el rival;
    - ambiguo: TheSportsDB lista el nombre exacto más de una vez en el equipo;
    - ok: presente en el equipo (`_persona_coincide` solo como cordura del id);
    - ausente: no aparece (en TheSportsDB, recortada, eso no confirma nada)."""
    nombre_f = _FUENTE_NOMBRE.get(fuente, fuente)
    jugador = str(sujeto.get("jugador") or "")
    pid = "" if fuente == "tsdb" else str((sujeto.get("ids") or {}).get(fuente) or "").strip()
    base = {"fuente": fuente, "id": pid or None, "nombre": None, "equipo": None, "rol": None, "entro": None}
    if summary is None:
        return {**base, "estado": "caida", "nota": f"{nombre_f} no respondió (sin alineaciones)"}
    equipos = summary.get("equipos") or {}
    if not equipos:
        return {**base, "estado": "caida", "nota": f"{nombre_f} no publicó alineaciones"}
    if fuente != "tsdb" and not pid:
        return {**base, "estado": "sin_id", "nota": f"el sujeto no trae ids.{fuente}: no se localiza por nombre"}
    if equipo not in equipos:
        lista = ", ".join(e.get("nombre") or k for k, e in equipos.items())
        return {**base, "estado": "discrepa",
                "nota": f"no ubico a {sujeto.get('equipo')} entre los equipos de {nombre_f} ({lista}): sin cruce claro o ambiguo"}
    propio = equipos[equipo]
    nombre_eq = propio.get("nombre") or equipo
    if fuente == "tsdb":
        return _localizar_por_nombre(summary, jugador, equipo, base)

    hits = [(k, e["jugadores"][pid]) for k, e in equipos.items() if pid in (e.get("jugadores") or {})]
    if len(hits) > 1:
        return {**base, "estado": "discrepa", "nota": f"el id {pid} aparece en los dos equipos de {nombre_f}"}
    if hits:
        k, fila = hits[0]
        nombre, eq_fila = str(fila.get("nombre") or ""), equipos[k].get("nombre") or k
        rol, entro = _rol(fila)
        out = {**base, "nombre": nombre, "equipo": eq_fila, "rol": rol, "entro": entro}
        if not (_persona_coincide(jugador, nombre) or _nombre_identico(jugador, nombre)):
            return {**out, "estado": "discrepa", "nota": f"el id {pid} es {nombre} ({eq_fila}) en {nombre_f}, no {jugador}"}
        if k != equipo:
            return {**out, "estado": "otro_equipo",
                    "nota": f"{nombre} (id {pid}) aparece con {eq_fila} en {nombre_f}, no con {nombre_eq}"}
        return {**out, "estado": "ok", "nota": f"{nombre} (id {pid}, {nombre_eq}, {_rol_txt(rol, entro)})"}
    mismos = [f for f in (propio.get("jugadores") or {}).values() if _nombre_identico(jugador, str(f.get("nombre") or ""))]
    if mismos:
        otros = ", ".join(f"id {f.get('id') or '?'}" for f in mismos)
        return {**base, "estado": "discrepa",
                "nota": f"el id {pid} no está en la convocatoria de {nombre_f}, pero sí un {mismos[0].get('nombre')} "
                        f"de {nombre_eq} con otro id ({otros}): ¿id equivocado?"}
    return {**base, "estado": "ausente", "nota": f"{jugador} (id {pid}) no aparece en la convocatoria de {nombre_eq} publicada por {nombre_f}"}


def _localizar_por_nombre(summary: dict, jugador: str, equipo: str, base: dict) -> dict:
    """TheSportsDB (sin ids): nombre normalizado idéntico y único dentro del
    equipo, en la alineación o, si no, entre sus goleadores (un gol también
    prueba presencia). Nunca subconjuntos ni similitud."""
    equipos = summary["equipos"]
    nombre_eq = equipos[equipo].get("nombre") or equipo

    def filas(e: dict) -> list[dict]:
        return [f for f in e.get("filas") or [] if _nombre_identico(jugador, str(f.get("nombre") or ""))]

    propias = filas(equipos[equipo])
    if len(propias) > 1:
        return {**base, "estado": "ambiguo",
                "nota": f"{len(propias)} jugadores de {nombre_eq} con el nombre exacto '{jugador}' en TheSportsDB (sin ids)"}
    if propias:
        rol, entro = _rol({**propias[0], "entro": None})
        return {**base, "estado": "ok", "nombre": propias[0]["nombre"], "equipo": nombre_eq, "rol": rol, "entro": entro,
                "nota": f"{propias[0]['nombre']} ({nombre_eq}, {_rol_txt(rol, entro)}; nombre exacto, sin ids)"}
    goles = [g for g in summary.get("goles") or []
             if "own" not in (g.get("tipo") or "").lower() and _nombre_identico(jugador, str(g.get("jugador") or ""))
             and normalizar(str(g.get("equipo") or "")) == normalizar(nombre_eq)]
    if goles:
        return {**base, "estado": "ok", "nombre": goles[0]["jugador"], "equipo": nombre_eq, "rol": None, "entro": True,
                "nota": f"{goles[0]['jugador']} ({nombre_eq}, {_rol_txt(None, True)}; nombre exacto, sin ids)"}
    otros = [e.get("nombre") or k for k, e in equipos.items() if k != equipo and filas(e)]
    if otros:
        return {**base, "estado": "otro_equipo",
                "nota": f"TheSportsDB (sin ids) lista un '{jugador}' con {otros[0]}, no con {nombre_eq}"}
    return {**base, "estado": "ausente",
            "nota": f"{jugador} no aparece en la alineación de {nombre_eq} de TheSportsDB (recorta el listado: no confirma ausencias)"}


def goles_del_jugador(summary: dict | None, equipo: str | None, loc: dict, autogoles: bool = False) -> list[dict]:
    """Goles del jugador ya localizado (estado ok) en `equipo`. ESPN/UEFA: por
    `jugador_id` (solo el goleador) y, si la fuente lo trae, `equipo_id`;
    TheSportsDB: nombre idéntico y mismo equipo. Los autogoles no cuentan salvo
    `autogoles=True` (solo para probar participación, y solo por id)."""
    equipos = (summary or {}).get("equipos") or {}
    if loc.get("estado") != "ok" or equipo not in equipos:
        return []
    eq = equipos[equipo]
    out = []
    for g in summary.get("goles") or []:
        autogol = "own" in (g.get("tipo") or "").lower()
        if loc.get("id"):
            if str(g.get("jugador_id") or "") != loc["id"]:
                continue
            if autogol:
                if autogoles:
                    out.append(g)
                continue
            if g.get("equipo_id") and eq.get("id") and str(g["equipo_id"]) != str(eq["id"]):
                continue
            out.append(g)
        elif not autogol and _nombre_identico(str(loc.get("nombre") or ""), str(g.get("jugador") or "")) \
                and normalizar(str(g.get("equipo") or "")) == normalizar(eq.get("nombre") or equipo):
            out.append(g)
    return out


def goles_incompletos(summary: dict | None, partido: Partido, equipo: str | None, loc: dict) -> str | None:
    """Motivo por el que la lista de goles de UNA fuente no alcanza para un NO
    de gol (None si alcanza): publica menos goles (autogoles incluidos) que el
    marcador, o, en una fuente con ids (ESPN/UEFA), un gol del equipo del sujeto
    sin id del goleador, que goles_del_jugador no puede atribuir. Una fuente
    recortada (TheSportsDB) no pasa por aquí: su NO nunca es alta."""
    if loc.get("estado") != "ok" or not (summary or {}).get("completo", True):
        return None
    goles = summary.get("goles") or []
    total = (partido.home_score or 0) + (partido.away_score or 0)
    if len(goles) < total:
        return f"publicó {len(goles)} goles de un partido con marcador {partido.marcador}"
    if not loc.get("id"):
        return None
    eq = ((summary.get("equipos") or {}).get(equipo)) or {}
    for g in goles:
        if "own" in (g.get("tipo") or "").lower() or str(g.get("jugador_id") or "").strip():
            continue
        if g.get("equipo_id") and eq.get("id"):
            propio = str(g["equipo_id"]) == str(eq["id"])
        elif g.get("equipo") and eq.get("nombre"):
            propio = normalizar(str(g["equipo"])) == normalizar(eq["nombre"])
        else:
            propio = True  # sin equipo publicado: no se puede descartar que sea del sujeto
        if propio:
            return f"publicó un gol ({g.get('minuto') or '?'}, {g.get('jugador') or '?'}) sin id del goleador"
    return None


def sugerir_titular(jugador: str, summary: dict | None, equipo: str | None, loc: dict) -> tuple[str | None, str]:
    """('YES'|'NO'|None, detalle) de UNA fuente para el jugador ya localizado
    (localizar_en_partido) en `equipo`. Ausente de una convocatoria completa →
    NO (no ser convocado resuelve NO); de una recortada (TheSportsDB) → None."""
    nombre_f = _FUENTE_NOMBRE.get(loc.get("fuente"), loc.get("fuente"))
    estado = loc.get("estado")
    if estado == "ok":
        nombre_eq = loc.get("equipo") or equipo
        if loc.get("rol") == "titular":
            return "YES", f"{loc['nombre']} en el once inicial de {nombre_eq}"
        if loc.get("rol") == "banca":
            return "NO", f"{loc['nombre']} en la banca de {nombre_eq} (no titular)"
        return None, f"{nombre_f} no lo muestra en la alineación ({loc.get('nota')})"
    if estado == "ausente" and (summary or {}).get("completo", True):
        return "NO", f"{jugador} no aparece en la convocatoria publicada por {nombre_f}"
    return None, loc.get("nota") or f"{jugador} no localizado en {nombre_f}"


def participo(jugador: str, summary: dict | None, equipo: str | None, loc: dict) -> bool | None:
    """True si fue titular, entró de cambio o tiene un gol (o autogol) por id;
    False si estuvo en la banca sin entrar según una fuente que publica cambios,
    o no está en una convocatoria completa; None si la fuente no lo informa."""
    estado = loc.get("estado")
    if estado == "ausente":
        return False if (summary or {}).get("completo", True) else None
    if estado != "ok":
        return None
    if loc.get("rol") == "titular" or loc.get("entro") is True:
        return True
    if goles_del_jugador(summary, equipo, loc, autogoles=True):
        return True
    if loc.get("rol") == "banca" and loc.get("entro") is False and (summary or {}).get("publica_cambios"):
        return False
    return None


def sugerir_gol(jugador: str, summary: dict | None, equipo: str | None, loc: dict) -> tuple[str | None, str]:
    """('YES'|'NO'|None, detalle) de UNA fuente: goles del jugador localizado en
    `equipo` (goles_del_jugador; nunca el de un homónimo del rival ni el del
    asistente). Sin localización ok → None."""
    nombre_f = _FUENTE_NOMBRE.get(loc.get("fuente"), loc.get("fuente"))
    if loc.get("estado") != "ok":
        return None, loc.get("nota") or f"{jugador} no localizado en {nombre_f}"
    nombre_eq = loc.get("equipo") or equipo
    propios = goles_del_jugador(summary, equipo, loc)
    if propios:
        return "YES", "; ".join(f"gol {g.get('minuto')} ({g.get('tipo')})" for g in propios) + f" de {loc['nombre']} ({nombre_eq})"
    goles = (summary or {}).get("goles") or []
    return "NO", f"sin gol de {jugador} ({nombre_eq}) en los goles de {nombre_f} ({len(goles)} goles en el partido)"


def resolver_accesorio(mercado: dict, spec: dict, tipo: str, partido: Partido, espn: dict | None,
                       segunda: dict | None, sujeto: dict, nota_segunda: str = "") -> dict:
    """Accesorio titular/gol con dos fuentes: ESPN + UEFA (sus competencias) o
    TheSportsDB (el resto). `partido` sale de `sujeto.equipo` + `rival`; el
    equipo del sujeto se ubica en cada resumen (equipo_en_resumen) y el jugador
    por id (localizar_en_partido). Reglas (D1/D2):
    - otro_equipo / discrepa / sin_id / ambiguo / caida en cualquier fuente →
      escalado SIN sugerencia (la razón lleva las notas de ambas);
    - ok en una y ausente en la otra → escalado SIN sugerencia;
    - ausente en ambas → escalado, nunca alta, con sugerencia NO (titular) o
      CANCELAR (gol) porque el partido salió del equipo del sujeto;
    - ok en ambas: falta el dato (sin rol, o un NO de gol con la lista de goles
      incompleta en esa fuente: goles_incompletos) → sin sugerencia; veredictos distintos → escalado con la de ESPN; YES igual →
      alta (TheSportsDB solo confirma presencias: su YES sí cuenta); titular NO
      → alta solo con UEFA; gol NO → alta solo si ambas confirman que participó,
      si no escalado con NO (entró según ESPN) o CANCELAR (no entró).
    Toda salida lleva `sujeto_confirmado` {jugador, equipo, partido, espn?,
    uefa?|tsdb?} (bloque por fuente solo con estado ok) y la identidad en
    `resultado`. `nota_segunda` explica por qué no hay segunda fuente."""
    base = {"id": mercado["id"], "pregunta": mercado.get("question"), "liga": mercado.get("subcategory"),
            "volume": round(float(mercado.get("volume") or 0)), "num_trades": int(mercado.get("num_trades") or 0)}
    marcador = f"{partido.marcador} ({fecha_corta(partido.kickoff)})"
    jugador = sujeto["jugador"]
    f2 = (segunda or {}).get("fuente") or ("uefa" if mercado.get("subcategory") in UEFA_COMPETICION else "tsdb")
    n2 = _FUENTE_NOMBRE.get(f2, f2)
    urls = {"fuente_1": espn["url"] if espn else partido.url}
    if segunda:
        urls["fuente_2"] = segunda["url"]
    lado = lado_del_equipo(partido, sujeto["equipo"])
    confirmado: dict = {"jugador": jugador, "equipo": lado["nombre"] if lado else sujeto["equipo"],
                        "partido": f"{partido.home} vs {partido.away}"}
    esc = {**base, "escalar": True, **urls, "sujeto_confirmado": confirmado}
    if lado is None:
        return {**esc, "razon": f"no pude ubicar a {sujeto['equipo']} en {partido.home} vs {partido.away}, sin sugerencia",
                "resultado": marcador}

    nombres = [sujeto["equipo"], lado["nombre"]]
    k_e, k_2 = equipo_en_resumen(espn, nombres), equipo_en_resumen(segunda, nombres)
    loc_e = localizar_en_partido(espn, sujeto, "espn", k_e)
    loc_2 = localizar_en_partido(segunda, sujeto, f2, k_2)
    if segunda is None and nota_segunda:
        loc_2 = {**loc_2, "nota": nota_segunda}
    notas = f"ESPN: {loc_e['nota']}; {n2}: {loc_2['nota']}"
    for loc in (loc_e, loc_2):
        if loc["estado"] == "ok":
            confirmado[loc["fuente"]] = {"id": loc["id"], "nombre": loc["nombre"], "equipo": lado["nombre"],
                                         "equipo_fuente": loc["equipo"]}
    partes = [lado["nombre"]] + [f"{_FUENTE_NOMBRE[f]} {confirmado[f]['id']}" for f in ("espn", "uefa") if f in confirmado]
    if "tsdb" in confirmado:
        partes.append("TheSportsDB por nombre exacto")
    ident = f"{jugador} ({' · '.join(partes)})"
    completo2 = bool(segunda) and segunda.get("completo", True)
    sugerir = sugerir_titular if tipo == "titular" else sugerir_gol
    ee, e2 = loc_e["estado"], loc_2["estado"]

    if ee in _SIN_IDENTIDAD or e2 in _SIN_IDENTIDAD:
        evidencia = "; ".join(f"{_FUENTE_NOMBRE[loc['fuente']]}: {sugerir(jugador, s, k, loc)[1]}"
                              for loc, s, k in ((loc_e, espn, k_e), (loc_2, segunda, k_2)) if loc["estado"] == "ok")
        return {**esc, "razon": f"identidad no confirmada en las dos fuentes, sin sugerencia ({notas})",
                "resultado": f"{marcador} — {ident}" + (f": {evidencia}" if evidencia else "")}
    if ee == "ausente" and e2 == "ausente":
        sug, efecto = (("NO", "no ser convocado resuelve NO") if tipo == "titular"
                       else ("CANCELAR", "sin participar, por normas se cancela"))
        aviso = "" if completo2 else f"; {n2} recorta el listado y no confirma ausencias"
        return {**esc, "veredicto_sugerido": sug,
                "razon": (f"partido identificado por equipo ({lado['nombre']}: {partido.marcador}); {jugador} no aparece "
                          f"en la convocatoria de ESPN ni en la de {n2} ({efecto}): confirmar que no fue convocado"
                          f"{aviso} ({notas})"),
                "resultado": f"{marcador} — {jugador}: ausente de ambas convocatorias"}
    if ee != e2:  # ok en una, ausente en la otra
        tiene, falta = ("ESPN", n2) if ee == "ok" else (n2, "ESPN")
        loc, s, k = (loc_e, espn, k_e) if ee == "ok" else (loc_2, segunda, k_2)
        aviso = f" ({n2} recorta el listado y solo confirma presencias)" if ee == "ok" and not completo2 else ""
        return {**esc, "razon": f"{jugador} aparece en {tiene} pero no en {falta}{aviso}, sin sugerencia ({notas})",
                "resultado": f"{marcador} — {ident}: {tiene} {sugerir(jugador, s, k, loc)[1]}"}

    v1, d1 = sugerir(jugador, espn, k_e, loc_e)
    v2, d2 = sugerir(jugador, segunda, k_2, loc_2)
    if tipo == "gol":
        # un NO exige la lista de goles completa en ESA fuente (D1): un gol que
        # falta o sin id del goleador no se le puede descartar al sujeto.
        if v1 == "NO" and (motivo := goles_incompletos(espn, partido, k_e, loc_e)):
            v1, d1 = None, f"ESPN {motivo}"
        if v2 == "NO" and (motivo := goles_incompletos(segunda, partido, k_2, loc_2)):
            v2, d2 = None, f"{n2} {motivo}"
    resultado = f"{marcador} — {ident}: {d1}; {n2}: {d2}"
    if v1 is None or v2 is None:
        return {**esc, "razon": f"falta el dato en ESPN o en {n2}, sin sugerencia (ESPN: {d1}; {n2}: {d2})",
                "resultado": resultado}
    if v1 != v2:
        razon = (f"{n2} recorta los goles y solo confirma presencias; ESPN dice {v1} ({d1}): confirmar con la página oficial"
                 if tipo == "gol" and not completo2 and v2 == "NO"
                 else f"las fuentes discrepan: ESPN {v1} ({d1}) vs {n2} {v2} ({d2})")
        return {**esc, "veredicto_sugerido": v1, "razon": razon, "resultado": resultado}
    alta = {**base, "veredicto": v1, "resultado": resultado, **urls, "confianza": "alta", "sujeto_confirmado": confirmado}
    if v1 == "YES":
        return alta
    if tipo == "titular":
        if completo2:
            return alta
        return {**esc, "veredicto_sugerido": "NO", "resultado": resultado,
                "razon": f"banca según ESPN y {n2}, pero {n2} solo confirma presencias (titular YES): confirmar con la página oficial"}
    # gol NO en ambas: NO alta solo si las dos confirman que participó.
    p1, p2 = participo(jugador, espn, k_e, loc_e), participo(jugador, segunda, k_2, loc_2)
    if completo2 and p1 is True and p2 is True:
        return alta
    sug = {"veredicto_sugerido": "NO"} if p1 is True else {"veredicto_sugerido": "CANCELAR"} if p1 is False else {}
    motivo = "entró o fue titular según ESPN" if p1 else ("no entró según ESPN" if p1 is False else "ESPN no informa si entró")
    razon = (f"sin gol en ESPN ni en {n2}, pero {n2} recorta los goles y solo confirma presencias ({motivo}): confirmar con la página oficial"
             if not completo2 else
             f"sin gol en ambas fuentes, pero la participación no está confirmada por las dos: {motivo} y {n2} no publica cambios")
    return {**esc, **sug, "razon": razon, "resultado": resultado}


def emparejar_uefa(partido: Partido, uefa: list[dict], tolerancia_h: float = 3) -> dict | None:
    """Partido de la UEFA que corresponde al de ESPN: mismo kickoff (±3 h) y
    ambos equipos con similitud ≥ UMBRAL contra cualquiera de sus alias. None si
    no hay cruce o si un segundo candidato queda ≥ UMBRAL a menos de 0.15
    (ambiguo: el resolvedor escala sin segunda fuente)."""
    puntuados = []
    for u in uefa:
        if abs((u["kickoff"] - partido.kickoff).total_seconds()) > tolerancia_h * 3600:
            continue
        sh = max((similitud(partido.home, n) for n in u["home"]), default=0.0)
        sa = max((similitud(partido.away, n) for n in u["away"]), default=0.0)
        puntuados.append((min(sh, sa), u))
    puntuados.sort(key=lambda t: t[0], reverse=True)
    if not puntuados or puntuados[0][0] < UMBRAL:
        return None
    if len(puntuados) > 1 and puntuados[1][0] >= UMBRAL and puntuados[0][0] - puntuados[1][0] < 0.15:
        return None
    return puntuados[0][1]
