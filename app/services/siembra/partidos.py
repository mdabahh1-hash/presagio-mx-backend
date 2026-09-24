"""Generador de 1X2 de fútbol para el agente de siembra (sin LLM, sin tokens).

Por cada liga de fútbol que esté en `fuentes.LIGAS` y en `plantillas.COMPETENCIAS`
lee el scoreboard de ESPN de los partidos que empiezan entre 24 h y 8 días
después, y arma un doc `tipo: partido` del sembrador por partido. Criterios en
agente-mercados/CRITERIOS-DE-MERCADOS.md (§7 «siempre entra»: la jornada
completa, exento del filtro de tendencia).

Prior con dos fuentes (Mark, 24-sep-2026): abre con las cuotas de DraftKings que
ESPN publica en el scoreboard, sin el margen de la casa, y lo compara con un
modelo de la tabla de ESPN. Sin cuotas o sin el equipo en la tabla → descartado;
diferencia > 15 puntos en alguna opción o tabla con < 3 partidos → «revisar».
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import yaml

from app.services.resolucion.fuentes import (
    LIGAS, SCHEDULED, Http, Partido, deporte, espn_scoreboard, espn_tabla, variantes_nombre,
)
from seeds.plantillas import COMPETENCIAS
from seeds.schema import QUESTION_MAX, SchemaError, cargar_texto

LIGAS_FUTBOL = [l for l in LIGAS if l in COMPETENCIAS and deporte(l) == "futbol"]
DESDE_H, HASTA_D = 24, 8          # ventana de publicación (§5: partido ≥ 24 h)
UMBRAL_REVISAR = 15               # puntos de diferencia cuotas vs tabla
MIN_PJ = 3
VENTAJA_LOCAL = 0.35              # puntos por partido
_MX = timezone(timedelta(hours=-6))
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def prob_americana(odds: str) -> float:
    s = str(odds).strip().upper()
    v = 100 if s in ("EVEN", "EV", "PK") else int(s.replace("+", ""))
    return 100 / (v + 100) if v > 0 else -v / (-v + 100)


def prob_cuotas(cuotas: dict | None) -> tuple[float, float, float] | None:
    """Moneyline americana → probabilidades sin margen (suman 1)."""
    try:
        ps = [prob_americana(cuotas[k]) for k in ("local", "empate", "visitante")]
    except (KeyError, ValueError, TypeError):
        return None
    t = sum(ps)
    return (ps[0] / t, ps[1] / t, ps[2] / t)


def prob_tabla(loc: dict | None, vis: dict | None) -> tuple[float, float, float] | None:
    """Modelo de puntos por partido + ventaja de local. None con < MIN_PJ jugados.
    ponytail: modelo simple de ppg; cambiar por Elo si los 1X2 abren mal calibrados."""
    if not loc or not vis or min(loc["pj"], vis["pj"]) < MIN_PJ:
        return None
    diff = loc["pts"] / loc["pj"] - vis["pts"] / vis["pj"] + VENTAJA_LOCAL
    empate = max(0.18, 0.27 - 0.05 * abs(diff))
    local = (1 - empate) / (1 + math.exp(-1.1 * diff))
    return (local, empate, 1 - empate - local)


def ints_100(ps) -> list[int]:
    """Porcentajes enteros que suman 100 (residuo mayor), ninguno en 0."""
    crudos = [p * 100 for p in ps]
    out = [int(c) for c in crudos]
    for i in sorted(range(len(ps)), key=lambda i: crudos[i] - out[i], reverse=True)[: 100 - sum(out)]:
        out[i] += 1
    for i, v in enumerate(out):
        if v < 1:
            out[i] = 1
            out[out.index(max(out))] -= 1 - v
    return out


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _fecha(d: datetime) -> str:
    return f"{d.day} de {_MESES[d.month - 1]} de {d.year}"


def _norm(s: str) -> str:
    return slug(s).replace("-", " ")


def es_duplicado(p: Partido, liga: str, existentes: list[dict]) -> bool:
    """Mismo partido ya abierto con otro id: misma subcategoría, kickoff a ±6 h y el
    nombre de un equipo en las etiquetas de sus opciones."""
    sub = COMPETENCIAS[liga].subcategoria
    nombres = {_norm(n) for n in variantes_nombre(p.home, p.away) + [a for a in p.alias if len(a) >= 4]}
    nombres.discard("")
    for m in existentes:
        if m["subcategory"] != sub or abs((m["kickoff_at"] - p.kickoff).total_seconds()) > 6 * 3600:
            continue
        etiquetas = " ".join(_norm(l) for l in m["labels"])
        if any(f" {n} " in f" {etiquetas} " for n in nombres):
            return True
    return False


def id_partido(p: Partido, liga: str) -> str:
    return f"{slug(liga)}-{slug(p.home)}-{slug(p.away)}-{p.kickoff.astimezone(_MX):%Y%m%d}"


def _texto_equipo(nombre: str, t: dict) -> str:
    donde = "de su conferencia" if t["grupos"] > 1 else "de la tabla"
    return f"{nombre} es {t['rank']}º {donde} con {t['pts']} puntos en {t['pj']} partidos"


def propuesta(p: Partido, liga: str, tabla: dict, ahora: datetime) -> tuple[dict | None, str | None]:
    """(propuesta, None) o (None, motivo de descarte)."""
    cuotas = prob_cuotas(p.cuotas)
    if cuotas is None:
        return None, "sin cuotas de DraftKings en ESPN"
    loc, vis = (tabla.get(i) for i in (p.equipo_ids or ("", "")))
    if not loc or not vis:
        return None, "sin tabla de ESPN para uno de los equipos"
    revisar = []
    t = prob_tabla(loc, vis)
    if t is None:
        revisar.append(f"tabla con menos de {MIN_PJ} partidos jugados")
    else:
        dif = max(abs(a - b) for a, b in zip(cuotas, t)) * 100
        if dif > UMBRAL_REVISAR:
            revisar.append(f"cuotas y tabla difieren {dif:.0f} puntos")
    pct = ints_100(cuotas)
    k = p.kickoff.astimezone(_MX)
    fin = k + timedelta(days=3)
    ventana = (f"la ventana del {k.day} al {_fecha(fin)}" if k.month == fin.month
               else f"la ventana del {_fecha(k)} al {_fecha(fin)}")
    context = (
        f"{_texto_equipo(p.home, loc)}; {_texto_equipo(p.away, vis)}, según la tabla de ESPN al "
        f"{_fecha(ahora.astimezone(_MX))}. Las cuotas de DraftKings publicadas por ESPN ese día daban "
        f"{pct[0]}% a {p.home}, {pct[1]}% al empate y {pct[2]}% a {p.away}."
    )
    doc = {
        "tipo": "partido",
        "id": id_partido(p, liga),
        "competencia": liga, "local": p.home, "visitante": p.away,
        "kickoff": p.kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pct": pct, "ventana": ventana, "context": context,
    }
    try:
        specs, _ = cargar_texto(_yaml([doc]))
    except SchemaError as e:
        return None, "; ".join(e.errores)[:300]
    if len(specs[0].question) > QUESTION_MAX:  # el runner rechazaría la tanda entera
        return None, f"pregunta de {len(specs[0].question)} caracteres (máximo {QUESTION_MAX})"
    return {
        "doc": doc, "liga": liga, "local": p.home, "visitante": p.away, "kickoff": doc["kickoff"],
        "cuotas": pct, "tabla": ints_100(t) if t else None, "revisar": revisar, "url": p.url,
    }, None


def _yaml(docs: list[dict]) -> str:
    return yaml.safe_dump_all(docs, allow_unicode=True, sort_keys=False)


def armar_propuestas(http: Http, ahora: datetime, excluir: set[str], existentes: list[dict],
                     ligas: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Síncrono (urllib): llamarlo con asyncio.to_thread. `excluir` = ids ya
    sembrados o ya propuestos; `existentes` = partidos abiertos
    {subcategory, kickoff_at, labels} para detectar el mismo partido con otro id."""
    desde, hasta = ahora + timedelta(hours=DESDE_H), ahora + timedelta(days=HASTA_D)
    propuestas: list[dict] = []
    descartes: list[dict] = []
    for liga in ligas or LIGAS_FUTBOL:
        try:
            partidos = [p for p in espn_scoreboard(http, liga, desde, hasta)
                        if p.estado == SCHEDULED and desde <= p.kickoff <= hasta]
            tabla = espn_tabla(http, liga) if partidos else {}
        except RuntimeError as e:
            descartes.append({"liga": liga, "partido": "(toda la liga)", "motivo": f"ESPN no respondió: {e}"[:300]})
            continue
        for p in partidos:
            if id_partido(p, liga) in excluir or es_duplicado(p, liga, existentes):
                continue
            prop, motivo = propuesta(p, liga, tabla, ahora)
            if prop is None:
                descartes.append({"liga": liga, "partido": f"{p.home} vs {p.away}", "kickoff": p.kickoff.isoformat(),
                                  "motivo": motivo})
            else:
                propuestas.append(prop)
    propuestas.sort(key=lambda x: (x["kickoff"], x["liga"]))
    return propuestas, descartes
