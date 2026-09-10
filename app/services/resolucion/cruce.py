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
