"""Emparejar mercados con partidos y derivar el veredicto. Funciones puras (sin red)
para poder testearlas.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from .fuentes import AET, CANCELLED, FT, LIVE, POSTPONED, SCHEDULED, Partido

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


# ── NFL: props de jugador (una sola fuente → escalado con sugerencia) ────────

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


def sugerir_prop_nfl(spec: dict, jugador_stats: dict) -> tuple[str, str]:
    """('YES'|'NO', detalle) a partir del box score del jugador (ya localizado)."""
    r, c, p = jugador_stats.get("rushing"), jugador_stats.get("receiving"), jugador_stats.get("passing")
    if spec["tipo"] == "td":
        n = _num(r, "rushingTouchdowns") + _num(c, "receivingTouchdowns")
        return ("YES" if n >= spec["umbral"] else "NO"), f"{n:.0f} TD por carrera/recepción (umbral {spec['umbral']:.0f})"
    if spec["tipo"] == "pases_td":
        n = _num(p, "passingTouchdowns")
        return ("YES" if n >= spec["umbral"] else "NO"), f"{n:.0f} pases de TD (umbral {spec['umbral']:.0f})"
    pts, detalle = fantasy_estandar(jugador_stats)
    return ("YES" if pts >= spec["umbral"] else "NO"), f"{pts:.2f} pts fantasy estándar (umbral {spec['umbral']:.1f}): {detalle}"


# ── accesorios (una sola fuente → siempre escalado con sugerencia) ───────────

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


def sugerir_titular(jugador: str, summary: dict) -> tuple[str | None, str]:
    """('YES'|'NO'|None, detalle) según las alineaciones de ESPN."""
    for equipo, r in summary.get("equipos", {}).items():
        for n in r.get("titulares", []):
            if _persona_coincide(jugador, n):
                return "YES", f"{n} en el once inicial de {equipo}"
        for n in r.get("banca", []):
            if _persona_coincide(jugador, n):
                return "NO", f"{n} en la banca de {equipo} (no titular)"
    if not summary.get("equipos"):
        return None, "ESPN no publicó alineaciones"
    return "NO", "no aparece en la convocatoria publicada por ESPN"


def sugerir_gol(jugador: str, summary: dict) -> tuple[str | None, str]:
    goles = summary.get("goles", [])
    propios = [g for g in goles if g.get("jugador") and _persona_coincide(jugador, g["jugador"]) and "own" not in (g.get("tipo") or "").lower()]
    if propios:
        return "YES", "; ".join(f"gol {g['minuto']} ({g['tipo']})" for g in propios)
    if not summary.get("equipos"):
        return None, "ESPN no publicó eventos del partido"
    return "NO", f"sin gol de {jugador} en los eventos clave de ESPN ({len(goles)} goles en el partido)"
