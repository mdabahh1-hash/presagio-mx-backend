"""Armar el plan de resoluciones a partir de los mercados pendientes.

Entrada: lista de mercados pendientes (formato de `agent-resolver.py list`,
detalle completo con outcomes y `sujeto`). Salida: dict con `resoluciones`
(1X2 / ganador con doble fuente coincidente; accesorios de jugador con el
partido elegido por `sujeto.equipo` + `rival` y la identidad confirmada por id
en ambas fuentes) y `escalados` (todo lo demás, con la evidencia que se haya
encontrado y, solo cuando la identidad no está en duda, un `veredicto_sugerido`).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from . import cruce
from .recetas import resolver_receta
from .sujeto import spec_de_pregunta, validar_sujeto
from .fuentes import (AET, CANCELLED, FT, LIGAS, LIVE, POSTPONED, UEFA_COMPETICION, Http, Partido, cbs_boxscore_nfl,
                      deporte, espn_boxscore_nfl, espn_scoreboard, espn_summary, tsdb_buscar, tsdb_resumen,
                      uefa_partidos, uefa_resumen, variantes_nombre)

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
            if m.get("auto_resolucion"):
                # Mercado de dato publicado con receta (no deportivo): dos fuentes
                # mecánicas como en deportes; una sola → escalado con sugerencia.
                _log(f"[receta] {m['id']}: {m['auto_resolucion'].get('fuente')}")
                entrada = resolver_receta(m, http)
                if entrada.pop("escalar", False):
                    escalados.append(entrada)
                else:
                    resoluciones.append(entrada)
            elif (m.get("category") or "").lower() in ("deportes", "sports"):
                escalados.append(_escalado(m, f"sin fuente automática para la subcategoría '{liga}'"))
            else:
                escalados.append(_escalado(m, "sin receta: resolver con la skill resolver-no-deportivos", sin_receta=True))
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

        segundas: dict[str, tuple[dict | None, str]] = {}  # id de partido ESPN → (resumen de la segunda fuente, nota)
        uefa_lista: list[dict] | None = None
        if liga in UEFA_COMPETICION and any(m.get("kind") == "accesorio" or m.get("market_type") == "binary" for m in ms):
            try:
                uefa_lista = uefa_partidos(http, liga, min(kickoffs), max(kickoffs))
                _log(f"[{liga}] {len(uefa_lista)} partidos en la UEFA")
            except RuntimeError as e:
                _log(f"[{liga}] UEFA no respondió: {e}")
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

            # Accesorios binarios de jugador (titular / gol): exigen `sujeto`. El
            # partido se elige por sujeto.equipo + rival (nunca buscando el nombre
            # en las alineaciones) y el jugador se ubica por id en ESPN y en la
            # segunda fuente; reglas de sugerencia en cruce.resolver_accesorio.
            spec = spec_de_pregunta(m.get("question"), liga)
            if not spec or spec.get("tipo") not in ("titular", "gol") or m.get("market_type") != "binary":
                escalados.append(_escalado(m, "accesorio sin regla mecánica: revisar a mano"))
                continue
            sujeto = m.get("sujeto")
            if not sujeto:
                escalados.append(_escalado(m, "accesorio de jugador sin sujeto (equipo, rival e ids): cargarlo con "
                                              "agent-resolver.py sujetos antes de resolver"))
                continue
            errs = validar_sujeto(spec, sujeto, liga)
            if errs:
                escalados.append(_escalado(m, f"sujeto inválido: {'; '.join(errs)}"))
                continue
            if sujeto.get("alcance") != "partido":
                escalados.append(_escalado(m, f"accesorio con alcance '{sujeto.get('alcance')}' (no de un solo partido): resolver a mano"))
                continue
            partido, nota = cruce.emparejar_cualquier_sede([sujeto["equipo"], sujeto["rival"]], kickoff, partidos)
            if partido is None:
                escalados.append(_escalado(m, f"partido {sujeto['equipo']} vs {sujeto['rival']}: {nota}"))
                continue
            if partido.estado in (POSTPONED, CANCELLED):
                escalados.append(_escalado(m, f"partido {partido.estado.lower()}: revisar la ventana de las normas", fuente_1=partido.url))
                continue
            if spec["tipo"] == "gol" and partido.estado != FT:
                razon = ("definido en prórroga: las normas cuentan solo los 90 minutos más el añadido" if partido.estado == AET
                         else f"partido no terminado ({partido.estado})")
                escalados.append(_escalado(m, razon, fuente_1=partido.url))
                continue
            if spec["tipo"] == "titular" and partido.estado not in (FT, AET, LIVE):
                escalados.append(_escalado(m, f"partido sin iniciar ({partido.estado}): alineación no confirmada", fuente_1=partido.url))
                continue
            try:
                summary = espn_summary(http, liga, partido.id)
            except RuntimeError as e:
                escalados.append(_escalado(m, f"ESPN summary falló: {e}", fuente_1=partido.url))
                continue
            # Segunda fuente: UEFA (oficial, alineaciones completas, ids) en sus
            # competencias; TheSportsDB (recortada, sin ids: solo presencias) en el resto.
            if partido.id not in segundas:
                segundas[partido.id] = _segunda_fuente_accesorio(http, liga, partido, uefa_lista)
            segunda, nota_segunda = segundas[partido.id]
            entrada = cruce.resolver_accesorio(m, spec, spec["tipo"], partido, summary, segunda, sujeto, nota_segunda)
            _log(f"    {m['id']}: {sujeto['jugador']} ({sujeto['equipo']}) → "
                 f"{entrada.get('veredicto') or 'escalado'}{'' if entrada.get('escalar') else ' (alta)'}")
            if entrada.pop("escalar", False):
                escalados.append(entrada)
            else:
                resoluciones.append(entrada)

    return {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modo": "plan-auto (ESPN + TheSportsDB)",
        "resoluciones": resoluciones,
        "escalados": escalados,
    }


def _segunda_fuente_accesorio(http: Http, liga: str, partido: Partido,
                              uefa_lista: list[dict] | None) -> tuple[dict | None, str]:
    """(resumen del mismo partido en la segunda fuente, nota si no hay). En las
    competencias de la UEFA solo cuenta la UEFA (los ids del sujeto son de ahí):
    si no respondió o el cruce es ambiguo no se cae a TheSportsDB."""
    if liga in UEFA_COMPETICION:
        if uefa_lista is None:
            return None, "la UEFA no respondió (lista de partidos)"
        u = cruce.emparejar_uefa(partido, uefa_lista)
        if u is None:
            _log(f"    ✗ UEFA: sin cruce claro para {partido.home} vs {partido.away}")
            return None, f"sin cruce claro (o ambiguo) para {partido.home} vs {partido.away} en la UEFA"
        try:
            r = uefa_resumen(http, liga, u)
            _log(f"    ✓ UEFA {partido.home} vs {partido.away}: {sum(len(e['titulares']) for e in r['equipos'].values())} titulares, {len(r['goles'])} goles")
            return r, ""
        except RuntimeError as e:
            _log(f"    ✗ UEFA lineups {partido.home} vs {partido.away}: {e}")
            return None, f"la UEFA no devolvió las alineaciones: {e}"
    ev = _buscar_tsdb(http, liga, partido, partido.home, partido.away, partido.kickoff)
    if ev is None:
        return None, "TheSportsDB no tiene el partido"
    try:
        return tsdb_resumen(http, ev.id), ""
    except RuntimeError as e:
        _log(f"    ✗ TSDB lineup/timeline {partido.home} vs {partido.away}: {e}")
        return None, f"TheSportsDB no devolvió alineación ni goles: {e}"


def _plan_nfl(http: Http, liga: str, ms: list[dict], partidos: list[Partido],
              resoluciones: list[dict], escalados: list[dict]) -> None:
    """NFL: el ganador se resuelve con doble fuente (ESPN + TheSportsDB) sobre
    outcomes por equipo. Las props (TD, pases de TD, fantasy) exigen `sujeto`:
    el partido se elige por `sujeto.equipo` + `rival` (nunca buscando el nombre
    en los box scores: caso Josh Allen / Josh Hines-Allen) y el jugador se
    localiza por id en ESPN y en CBS. Confianza alta solo con identidad
    confirmada en ambas; cualquier duda se escala (reglas en
    cruce.resolver_prop_nfl)."""
    boxscores: dict[str, dict] = {}
    cbs_cache: dict[str, dict | None] = {}

    def boxscore(p: Partido) -> dict | None:
        if p.id not in boxscores:
            try:
                boxscores[p.id] = espn_boxscore_nfl(http, liga, p.id)
            except RuntimeError as e:
                _log(f"    ✗ box score {p.home} vs {p.away}: {e}")
                boxscores[p.id] = None
        return boxscores[p.id]

    def cbs(p: Partido) -> dict | None:
        """Segunda fuente: box score de CBS del mismo partido (abreviaturas de ESPN)."""
        if p.id not in cbs_cache:
            cbs_cache[p.id] = None
            abbr_home, abbr_away = cruce.abbrs_partido(p)
            if abbr_home and abbr_away:
                try:
                    cbs_cache[p.id] = cbs_boxscore_nfl(http, p.kickoff, abbr_away, abbr_home)
                    _log(f"    ✓ CBS box score {p.home} vs {p.away}: {len(cbs_cache[p.id]['jugadores'])} jugadores")
                except RuntimeError as e:
                    _log(f"    ✗ CBS box score {p.home} vs {p.away}: {e}")
        return cbs_cache[p.id]

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
        # Identidad: sin sujeto no se adivina el jugador (ni por nombre ni por
        # cercanía del partido): escalado sin sugerencia.
        sujeto = m.get("sujeto")
        if not sujeto:
            escalados.append(_escalado(m, "prop de jugador sin sujeto (equipo, rival e ids): cargarlo con "
                                          "agent-resolver.py sujetos antes de resolver"))
            continue
        errs = validar_sujeto(spec, sujeto, liga)
        if errs:
            escalados.append(_escalado(m, f"sujeto inválido: {'; '.join(errs)}"))
            continue
        if sujeto.get("alcance") != "partido":
            escalados.append(_escalado(m, f"prop con alcance '{sujeto.get('alcance')}' (no de un solo partido): resolver a mano"))
            continue
        # Partido por equipo, en cualquier sede, cerca del cierre.
        elegido, nota = cruce.emparejar_cualquier_sede([sujeto["equipo"], sujeto["rival"]], kickoff, partidos)
        if elegido is None:
            escalados.append(_escalado(m, f"partido {sujeto['equipo']} vs {sujeto['rival']}: {nota}"))
            continue
        lado = cruce.lado_del_equipo(elegido, sujeto["equipo"])
        if lado is None or not lado.get("abbr"):
            escalados.append(_escalado(m, f"no pude ubicar a {sujeto['equipo']} (ni su abreviatura) en "
                                          f"{elegido.home} vs {elegido.away}", fuente_1=elegido.url))
            continue
        bs_e = boxscore(elegido)
        if bs_e is None:
            escalados.append(_escalado(m, "ESPN no devolvió el box score", fuente_1=elegido.url))
            continue
        if bs_e.get("estado") not in ("FT", "AET"):
            escalados.append(_escalado(m, f"partido no terminado ({bs_e.get('estado')})", fuente_1=bs_e["url"]))
            continue
        bs_c = cbs(elegido)
        loc_e = cruce.localizar_jugador(bs_e, sujeto, "espn", lado["abbr"])
        loc_c = cruce.localizar_jugador(bs_c, sujeto, "cbs", lado["abbr"])
        _log(f"    {m['id']}: {sujeto['jugador']} ({lado['abbr']}) ESPN {loc_e['estado']} · CBS {loc_c['estado']}")
        entrada = cruce.resolver_prop_nfl(m, spec, sujeto, elegido, lado, bs_e, bs_c, loc_e, loc_c)
        if entrada.pop("escalar", False):
            escalados.append(entrada)
        else:
            resoluciones.append(entrada)


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
