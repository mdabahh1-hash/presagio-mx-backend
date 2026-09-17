"""Marcador en vivo de los partidos en ventana, para la landing de Deportes.

Poller sin LLM: cada EN_VIVO_INTERVALO_SEGUNDOS toma los mercados `kind='partido'`
activos con kickoff_at entre 5 h antes y 30 min después de ahora, pide el
scoreboard de ESPN de cada liga (misma fuente y mismo cruce que la resolución:
fuentes.espn_scoreboard + cruce.emparejar / emparejar_cualquier_sede) y guarda en
memoria {market_id: EstadoEnVivo}. GET /api/markets/en-vivo lo sirve; sin
candidatos el dict queda vacío y el loop duerme más. Es informativo: un partido
en juego ya está PENDING_RESOLUTION (cierra al kickoff); por eso el tick cierra
primero los vencidos (el loop de mantenimiento tarda hasta 15 min).
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.market import Market, MarketStatus
from app.services.market_maintenance import _close_expired
from app.services.resolucion import cruce
from app.services.resolucion.fuentes import LIGAS, Http, Partido, deporte, espn_scoreboard
from app.services.resolucion.mercados import mercado_a_dict

logger = logging.getLogger("app.en_vivo")

VENTANA_ANTES = timedelta(hours=5)
VENTANA_DESPUES = timedelta(minutes=30)
SIN_CANDIDATOS_SEGUNDOS = 600
TIMEOUT_FUENTE_SEGUNDOS = 90  # Http.get duerme 30 s × intento ante un 429 de ESPN


@dataclass
class EstadoEnVivo:
    market_id: str
    estado: str
    local: str
    visitante: str
    marcador_local: int | None
    marcador_visitante: int | None
    reloj: str | None
    periodo: int | None
    fuente_url: str | None
    actualizado: str


# Se REEMPLAZA entero en cada tick (nunca se muta): los handlers lo leen en el loop principal.
_ESTADO: dict[str, EstadoEnVivo] = {}
_LAST: dict = {"ran_at": None, "candidatos": 0, "en_vivo": 0, "run_count": 0, "error": None}


def estados() -> list[dict]:
    return [asdict(e) for e in _ESTADO.values()]


def get_en_vivo_status() -> dict:
    return dict(_LAST)


async def candidatos(db, ahora: datetime) -> list[Market]:
    """Partidos (1X2 / ganador NFL) activos con kickoff en ventana y liga con fuente."""
    res = await db.execute(
        select(Market)
        .where(Market.kind == "partido")
        .where(Market.status.in_((MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION)))
        .where(Market.kickoff_at.is_not(None))
        .where(Market.kickoff_at >= ahora - VENTANA_ANTES)
        .where(Market.kickoff_at <= ahora + VENTANA_DESPUES)
        .options(selectinload(Market.outcomes))
    )
    return [m for m in res.scalars().all() if m.subcategory in LIGAS]


def _emparejar(liga: str, m: dict, kickoff: datetime, partidos: list[Partido]) -> Partido | None:
    if deporte(liga) == "nfl":
        outs = cruce.equipos_ganador(m)
        if not outs:
            return None
        p, _ = cruce.emparejar_cualquier_sede([n for _, n in outs], kickoff, partidos)
        return p
    eq = cruce.equipos_partido(m)
    if not eq:
        return None
    p, _ = cruce.emparejar(eq[0], eq[1], kickoff, partidos)
    return p


def _consultar(http: Http, por_liga: dict[str, list[dict]]) -> dict[str, EstadoEnVivo]:
    """Síncrono (urllib): corre en un hilo. Un scoreboard por liga, cruce por mercado."""
    ahora = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    out: dict[str, EstadoEnVivo] = {}
    for liga, ms in por_liga.items():
        kickoffs = [m["kickoff"] for m in ms]
        try:
            partidos = espn_scoreboard(http, liga, min(kickoffs), max(kickoffs))
        except RuntimeError as e:
            logger.warning("[en vivo] %s: ESPN no respondió: %s", liga, e)
            continue
        for m in ms:
            p = _emparejar(liga, m["dict"], m["kickoff"], partidos)
            if p is None:
                continue
            out[m["id"]] = EstadoEnVivo(
                market_id=m["id"], estado=p.estado, local=p.home, visitante=p.away,
                marcador_local=p.home_score, marcador_visitante=p.away_score,
                reloj=p.reloj, periodo=p.periodo, fuente_url=p.url, actualizado=ahora,
            )
    return out


async def tick(ahora: datetime | None = None) -> int:
    """Una pasada: cierra vencidos, busca candidatos, consulta ESPN y reemplaza el
    estado. Devuelve el número de candidatos (0 = dormir más)."""
    global _ESTADO
    ahora = ahora or datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        await _close_expired(db, ahora)
        await db.commit()
        ms = await candidatos(db, ahora)
        por_liga: dict[str, list[dict]] = defaultdict(list)
        for m in ms:
            por_liga[m.subcategory].append({"id": m.id, "kickoff": m.kickoff_at, "dict": mercado_a_dict(m, m.outcomes)})
    if not por_liga:
        _ESTADO = {}
    else:
        _ESTADO = await asyncio.wait_for(asyncio.to_thread(_consultar, Http(), dict(por_liga)), TIMEOUT_FUENTE_SEGUNDOS)
    _LAST.update(ran_at=ahora.isoformat(), candidatos=len(ms), en_vivo=sum(1 for e in _ESTADO.values() if e.estado == "LIVE"),
                 run_count=_LAST["run_count"] + 1, error=None)
    return len(ms)


async def en_vivo_loop() -> None:
    while True:
        n = 0
        try:
            n = await tick()
        except Exception as e:  # noqa: BLE001
            _LAST["error"] = str(e)
            logger.warning("[en vivo] error: %s", e)
        base = settings.EN_VIVO_INTERVALO_SEGUNDOS
        await asyncio.sleep(base if n else max(base, SIN_CANDIDATOS_SEGUNDOS))
