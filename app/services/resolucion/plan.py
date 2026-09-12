"""Armar el plan de resoluciones a partir de los mercados pendientes.

Entrada: lista de mercados pendientes (formato de `agent-resolver.py list`,
detalle completo con outcomes). Salida: dict con `resoluciones` (solo 1X2 con
doble fuente coincidente) y `escalados` (todo lo demás, con la evidencia que se
haya encontrado y, cuando aplica, un `veredicto_sugerido`).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from . import cruce
from .fuentes import (LIGAS, Http, Partido, deporte, espn_boxscore_nfl, espn_scoreboard, espn_summary,
                      tsdb_buscar, variantes_nombre)

logger = logging.getLogger(__name__)


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)


def _escalado(m: dict, razon: str, **extra) -> dict:
    return {"id": m["id"], "pregunta": m.get("question"), "liga": m.get("subcategory"), "razon": razon,
            "volume": round(float(m.get("volume") or 0)), "num_trades": int(m.get("num_trades") or 0), **extra}


def _log(msg: str) -> None:
    logger.info(msg)


def armar_plan(mercados: list[dict], http: Http | None = None, solo_ligas: set[str] | None = None) -> dict:
    http = http or Http()
    resoluciones: list[dict] = []
    escalados: list[dict] = []

    por_liga: dict[str, list[dict]] = defaultdict(list)
    for m in mercados:
        liga = m.get("subcategory") or ""
        if solo_ligas and liga not in solo_ligas:
            continue
        if liga not in LIGAS:
            escalados.append(_escalado(m, f"sin fuente automática para la subcategoría '{liga}'"))
            continue
        por_liga[liga].append(m)

    for liga, ms in por_liga.items():
        kickoffs = [_dt(m["ends_at"]) for m in ms]
        _log(f"[{liga}] {len(ms)} mercados · ESPN {min(kickoffs):%Y-%m-%d} → {max(kickoffs):%Y-%m-%d}")
        try:
            partidos = espn_scoreboard(http, liga, min(kickoffs), max(kickoffs))
        except RuntimeError as e:
            for m in ms:
                escalados.append(_escalado(m, f"ESPN no respondió: {e}"))
            continue
        _log(f"[{liga}] {len(partidos)} partidos en ESPN")

        if deporte(liga) == "nfl":
            _plan_nfl(http, liga, ms, partidos, resoluciones, escalados)
            continue

        for m in ms:
            kickoff = _dt(m["ends_at"])
            if m.get("market_type") == "multi" and (m.get("kind") == "partido" or cruce.equipos_partido(m)):
                eq = cruce.equipos_partido(m)
                if not eq:
                    escalados.append(_escalado(m, "no pude extraer local/visitante de la pregunta"))
                    continue
                local, visitante = eq
                espn, nota = cruce.emparejar(local, visitante, kickoff, partidos)
                tsdb: Partido | None = None
                if espn is not None:
                    tsdb = _buscar_tsdb(http, liga, espn, local, visitante, kickoff)
                entrada = cruce.resolver_1x2(m, espn, nota, tsdb)
                if entrada.pop("escalar", False):
                    escalados.append(entrada)
                else:
                    resoluciones.append(entrada)
                continue

            # Accesorios binarios: titular / gol → sugerencia con una fuente.
            tit = cruce.parse_titular(m)
            gol = None if tit else cruce.parse_gol(m)
            spec = tit or gol
            if not spec or m.get("market_type") != "binary":
                escalados.append(_escalado(m, "accesorio sin regla mecánica: revisar a mano"))
                continue
            summary = None
            if spec["equipos"]:
                partido = _partido_de_equipos(spec["equipos"], kickoff, partidos)
                if partido is None:
                    escalados.append(_escalado(m, f"no encontré en ESPN el partido {' vs '.join(spec['equipos'])}"))
                    continue
                try:
                    summary = espn_summary(http, liga, partido.id)
                except RuntimeError as e:
                    escalados.append(_escalado(m, f"ESPN summary falló: {e}", fuente_1=partido.url))
                    continue
            else:
                partido, summary = _partido_por_jugador(http, liga, spec["jugador"], kickoff, partidos)
                if partido is None:
                    escalados.append(_escalado(m, f"{spec['jugador']} no aparece en ninguna alineación de ESPN cerca del cierre"))
                    continue
            sugerido, detalle = (cruce.sugerir_titular if tit else cruce.sugerir_gol)(spec["jugador"], summary)
            escalados.append(_escalado(
                m, "accesorio con una sola fuente (ESPN): confirmar con la fuente oficial antes de resolver",
                veredicto_sugerido=sugerido, resultado=f"{partido.marcador} ({cruce.fecha_corta(partido.kickoff)}) — {detalle}",
                fuente_1=summary["url"],
            ))

    return {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modo": "plan-auto (ESPN + TheSportsDB)",
        "resoluciones": resoluciones,
        "escalados": escalados,
    }


def _plan_nfl(http: Http, liga: str, ms: list[dict], partidos: list[Partido],
              resoluciones: list[dict], escalados: list[dict]) -> None:
    """NFL: el ganador se resuelve con doble fuente (ESPN + TheSportsDB) sobre
    outcomes por equipo; las props (TD, pases de TD, fantasy) salen escaladas
    con sugerencia del box score de ESPN, como los accesorios de fútbol."""
    boxscores: dict[str, dict] = {}

    def boxscore(p: Partido) -> dict | None:
        if p.id not in boxscores:
            try:
                boxscores[p.id] = espn_boxscore_nfl(http, liga, p.id)
            except RuntimeError as e:
                _log(f"    ✗ box score {p.home} vs {p.away}: {e}")
                boxscores[p.id] = None
        return boxscores[p.id]

    for m in ms:
        kickoff = _dt(m["ends_at"])
        if m.get("market_type") == "multi":
            outs = cruce.equipos_ganador(m)
            if not outs:
                escalados.append(_escalado(m, "multi NFL sin dos outcomes de equipo: revisar a mano"))
                continue
            nombres = [n for _, n in outs]
            espn, nota = cruce.emparejar_cualquier_sede(nombres, kickoff, partidos)
            tsdb: Partido | None = None
            if espn is not None:
                tsdb = _buscar_tsdb(http, liga, espn, espn.home, espn.away, kickoff)
            entrada = cruce.resolver_ganador(m, outs, espn, nota, tsdb)
            if entrada.pop("escalar", False):
                escalados.append(entrada)
            else:
                resoluciones.append(entrada)
            continue

        spec = cruce.parse_prop_nfl(m)
        if not spec or m.get("market_type") != "binary":
            escalados.append(_escalado(m, "prop NFL sin regla mecánica: revisar a mano"))
            continue
        cercanos = sorted(
            (p for p in partidos if abs((p.kickoff - kickoff).total_seconds()) <= 36 * 3600),
            key=lambda p: abs((p.kickoff - kickoff).total_seconds()),
        )
        hallado = None
        for p in cercanos:
            bs = boxscore(p)
            if not bs:
                continue
            for nombre, stats in bs["jugadores"].items():
                if cruce._persona_coincide(spec["jugador"], nombre):
                    hallado = (p, bs, nombre, stats)
                    break
            if hallado:
                break
        if hallado is None:
            if not cercanos:
                escalados.append(_escalado(m, "ningún partido de la NFL cerca de la hora de cierre"))
            else:
                escalados.append(_escalado(
                    m, f"{spec['jugador']} no aparece en el box score de ESPN de los partidos cercanos: "
                       "si fue inactivo, por normas el mercado se cancela",
                    veredicto_sugerido="CANCELAR", fuente_1=cercanos[0].url,
                ))
            continue
        p, bs, nombre, stats = hallado
        if bs.get("estado") not in ("FT", "AET"):
            escalados.append(_escalado(m, f"partido no terminado ({bs.get('estado')})", fuente_1=bs["url"]))
            continue
        sugerido, detalle = cruce.sugerir_prop_nfl(spec, stats)
        escalados.append(_escalado(
            m, "prop con una sola fuente (box score de ESPN): confirmar con NFL.com o CBS antes de resolver",
            veredicto_sugerido=sugerido,
            resultado=f"{p.marcador} ({cruce.fecha_corta(p.kickoff)}) — {nombre}: {detalle}",
            fuente_1=bs["url"],
        ))


def _buscar_tsdb(http: Http, liga: str, espn: Partido, local: str, visitante: str, kickoff: datetime) -> Partido | None:
    """Segunda fuente: TheSportsDB con variantes de nombre (alias, sin siglas,
    nombre del mercado). El evento hallado debe ser el mismo partido en la
    misma orientación local/visitante."""
    sep = espn.alias.index("|") if "|" in espn.alias else len(espn.alias)
    corto_h = espn.alias[1] if sep > 1 else espn.home           # shortDisplayName
    corto_a = espn.alias[sep + 2] if len(espn.alias) > sep + 2 else espn.away
    homes = variantes_nombre(espn.home, local, corto_h)
    aways = variantes_nombre(espn.away, visitante, corto_a)
    try:
        p, n = tsdb_buscar(http, liga, homes, aways, kickoff)
    except RuntimeError as e:
        _log(f"    ✗ {espn.home} vs {espn.away}: TSDB error {e}")
        return None
    if p is not None and max(cruce.similitud(p.home, x) for x in homes) >= cruce.UMBRAL \
            and max(cruce.similitud(p.away, x) for x in aways) >= cruce.UMBRAL:
        _log(f"    ✓ {espn.home} vs {espn.away}: TSDB '{p.home} vs {p.away}' ({n} consultas)")
        return p
    _log(f"    ✗ {espn.home} vs {espn.away}: sin cruce en TSDB ({n} consultas)")
    return None


def _partido_por_jugador(http: Http, liga: str, jugador: str, kickoff: datetime,
                         partidos: list[Partido]) -> tuple[Partido | None, dict | None]:
    """Para accesorios sin equipo en la pregunta: busca al jugador en las
    alineaciones de los partidos de la liga cercanos al cierre."""
    cercanos = sorted(
        (p for p in partidos if abs((p.kickoff - kickoff).total_seconds()) <= 36 * 3600),
        key=lambda p: abs((p.kickoff - kickoff).total_seconds()),
    )
    for p in cercanos:
        try:
            summary = espn_summary(http, liga, p.id)
        except RuntimeError:
            continue
        for r in summary["equipos"].values():
            if any(cruce._persona_coincide(jugador, n) for n in r["titulares"] + r["banca"]):
                return p, summary
    return None, None


def _partido_de_equipos(equipos: list[str], kickoff: datetime, partidos: list[Partido]) -> Partido | None:
    """Partido cercano al kickoff donde aparezcan los equipos nombrados (cualquier orden)."""
    mejor, mejor_score = None, 0.0
    for p in partidos:
        if abs((p.kickoff - kickoff).total_seconds()) > 6 * 3600:
            continue
        scores = []
        for eq in equipos:
            scores.append(max(cruce.similitud(eq, p.home), cruce.similitud(eq, p.away)))
        s = min(scores) if scores else 0.0
        if s > mejor_score:
            mejor, mejor_score = p, s
    return mejor if mejor_score >= cruce.UMBRAL else None
