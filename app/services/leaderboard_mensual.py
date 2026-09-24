"""Leaderboard mensual con premios al top 3.

Ganancia del mes = Σ de los trades hechos en el mes calendario (CDMX) de
[valor(trade) − costo]. Solo hay compras, así que cada trade conserva sus
acciones hasta resolver:
  resuelto  → shares si ganó, 0 si no (lmsr.posicion_gana)
  cancelado → su costo (el reembolso lo devuelve: ganancia 0)
  sin resolver → shares × precio LMSR actual del lado comprado
Bonos, referidos y los 10k de registro no cuentan (no son trades).

El día 1 el loop de mantenimiento congela el mes anterior (`cerrar_mes_anterior`)
y manda a Mark un correo con enlace firmado; al aprobar (descalificando si hace
falta) el top 3 queda público en `/users/leaderboard/ganadores`.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import lmsr
from app.core.auth import ADMIN_EMAIL
from app.models.leaderboard_mes import LeaderboardMes, LeaderboardMesFila
from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome
from app.models.trade import Trade, TradeSide
from app.models.user import User

logger = logging.getLogger(__name__)

MX = ZoneInfo("America/Mexico_City")
MIN_PREDICCIONES = 10
MIN_MERCADOS = 5
PREMIADOS = 3
TOKEN_TYP = "leaderboard_approval"

_RESUELTOS = {MarketStatus.RESOLVED_YES: "YES", MarketStatus.RESOLVED_NO: "NO"}


def mes_de(dt: datetime) -> date:
    """Primer día del mes CDMX de `dt`."""
    return dt.astimezone(MX).date().replace(day=1)


def limites(mes: date) -> tuple[datetime, datetime]:
    """[inicio, fin) del mes en UTC; CDMX define dónde empieza y acaba."""
    sig = (mes.replace(day=28) + timedelta(days=4)).replace(day=1)
    a = datetime(mes.year, mes.month, 1, tzinfo=MX)
    b = datetime(sig.year, sig.month, 1, tzinfo=MX)
    return a.astimezone(timezone.utc), b.astimezone(timezone.utc)


def clave(mes: date) -> str:
    return mes.strftime("%Y-%m")


@dataclass
class Fila:
    user: User
    ganancia: float = 0.0
    volumen: float = 0.0
    n_trades: int = 0
    mercados: set | None = None
    elegible: bool = False
    rank: int | None = None

    @property
    def n_mercados(self) -> int:
        return len(self.mercados or ())


def valor_trade(t: Trade, m: Market, q_multi: dict[str, float] | None) -> float:
    """Lo que vale hoy un trade (en PT)."""
    side = t.side.value if t.side else None
    multi = m.market_type == "multi"
    if m.status == MarketStatus.CANCELLED:
        return t.cost
    ganador = _RESUELTOS.get(m.status) or (m.resolved_outcome_key if m.status == MarketStatus.RESOLVED else None)
    if ganador:
        return t.shares if lmsr.posicion_gana(side, t.outcome_key, ganador, multi) else 0.0
    # Sin resolver: marca LMSR, igual que `users._enrich_positions`.
    if multi:
        if not q_multi or t.outcome_key not in q_multi:
            return t.cost
        p = lmsr.outcome_price(q_multi, m.b, t.outcome_key)
        return t.shares * (1.0 - p if t.side == TradeSide.NO else p)
    p_yes = lmsr.yes_price(m.q_yes, m.q_no, m.b)
    return t.shares * (p_yes if (t.outcome_key or side) == "YES" else 1.0 - p_yes)


def asignar_ranks(filas: list[Fila]) -> None:
    """Ordena por ganancia y numera a los elegibles; empates comparten lugar
    (mismo criterio que `league_engine.maybe_resolve_cycle`)."""
    filas.sort(key=lambda f: (-f.ganancia, -f.volumen, f.user.id))
    rank, prev, n = 0, None, 0
    for f in filas:
        if not f.elegible:
            f.rank = None
            continue
        n += 1
        g = round(f.ganancia, 2)
        if g != prev:
            rank, prev = n, g
        f.rank = rank


async def ranking_mes(db: AsyncSession, mes: date) -> list[Fila]:
    """Todos los que operaron en el mes, ordenados; `rank` solo en elegibles.
    ponytail: carga todos los trades del mes en memoria; agregar en SQL si pasan de ~100k."""
    a, b = limites(mes)
    rows = (await db.execute(
        select(Trade, Market, User).join(Market, Market.id == Trade.market_id).join(User, User.id == Trade.user_id)
        .where(Trade.created_at >= a, Trade.created_at < b)
    )).all()
    multi_ids = {m.id for _, m, _ in rows if m.market_type == "multi"}
    q: dict[str, dict[str, float]] = {}
    if multi_ids:
        for o in (await db.execute(select(Outcome).where(Outcome.market_id.in_(multi_ids)))).scalars():
            q.setdefault(o.market_id, {})[o.outcome_key] = o.q

    por_user: dict[int, Fila] = {}
    for t, m, u in rows:
        f = por_user.setdefault(u.id, Fila(user=u, mercados=set()))
        f.ganancia += valor_trade(t, m, q.get(m.id)) - t.cost
        f.volumen += t.cost
        f.n_trades += 1
        f.mercados.add(m.id)
    filas = list(por_user.values())
    for f in filas:
        f.elegible = (f.n_trades >= MIN_PREDICCIONES and f.n_mercados >= MIN_MERCADOS
                      and f.user.email_verified and f.user.email != ADMIN_EMAIL)
    asignar_ranks(filas)
    return filas


# ── cierre y aprobación ──────────────────────────────────────────────────────

def url_aprobacion(cierre: LeaderboardMes) -> str:
    from app.services.resolucion.nocturno import make_plan_token
    return (f"{settings.BACKEND_URL}/api/admin/leaderboard/meses/{cierre.id}/aprobar"
            f"?t={make_plan_token(cierre.id, cierre.nonce, TOKEN_TYP)}")


async def cerrar_mes(db: AsyncSession, mes: date) -> LeaderboardMes | None:
    """Congela `mes` (solo elegibles). None si ya estaba cerrado. No manda correo."""
    if (await db.execute(select(LeaderboardMes).where(LeaderboardMes.mes == clave(mes)))).scalar_one_or_none():
        return None
    cierre = LeaderboardMes(mes=clave(mes), status="pending", nonce=secrets.token_urlsafe(16))
    db.add(cierre)
    for f in await ranking_mes(db, mes):
        if f.elegible:
            db.add(LeaderboardMesFila(
                mes=cierre.mes, user_id=f.user.id, ganancia=round(f.ganancia, 2), volumen=round(f.volumen, 2),
                n_trades=f.n_trades, n_mercados=f.n_mercados, rank=f.rank,
            ))
    await db.commit()
    await db.refresh(cierre)
    return cierre


async def filas_de(db: AsyncSession, mes: str, limite: int | None = None) -> list[tuple[LeaderboardMesFila, User]]:
    q = (select(LeaderboardMesFila, User).join(User, User.id == LeaderboardMesFila.user_id)
         .where(LeaderboardMesFila.mes == mes)
         .order_by(LeaderboardMesFila.descalificado, LeaderboardMesFila.rank, LeaderboardMesFila.id))
    return list((await db.execute(q.limit(limite) if limite else q)).all())


async def aprobar(db: AsyncSession, cierre: LeaderboardMes, descalificar: set[int]) -> None:
    """Marca descalificados, renumera a los demás y publica el mes."""
    filas = [fila for fila, _ in await filas_de(db, cierre.mes)]
    rank, prev, n = 0, None, 0
    for fila in sorted(filas, key=lambda x: (x.rank or 0, x.id)):
        fila.descalificado = fila.user_id in descalificar
        if fila.descalificado:
            fila.rank = None
            continue
        n += 1
        if fila.ganancia != prev:
            rank, prev = n, fila.ganancia
        fila.rank = rank
    cierre.status, cierre.aprobado_at = "approved", datetime.now(timezone.utc)
    await db.commit()


async def cerrar_mes_anterior() -> None:
    """Idempotente; lo llama el loop de mantenimiento cada 15 min. Cierra el mes
    anterior y manda el correo; si el enlace ya venció sin aprobarse, lo reenvía."""
    import app.database as app_db
    from app.services.email import send_leaderboard_cierre_email

    ahora = datetime.now(timezone.utc)
    anterior = (mes_de(ahora) - timedelta(days=1)).replace(day=1)
    if anterior < date(2026, 10, 1):  # primer mes con premios: octubre 2026
        return
    async with app_db.AsyncSessionLocal() as db:
        cierre = await cerrar_mes(db, anterior)
        if cierre is None:
            cierre = (await db.execute(select(LeaderboardMes).where(LeaderboardMes.mes == clave(anterior)))).scalar_one()
            vence = timedelta(hours=settings.PLAN_APPROVAL_TTL_HOURS)
            if cierre.status != "pending" or (cierre.correo_at and ahora - cierre.correo_at < vence):
                return
        top = [(f.rank, u.username, f.ganancia, f.n_trades, f.n_mercados) for f, u in await filas_de(db, cierre.mes, 10)]
        await send_leaderboard_cierre_email(cierre.mes, top, url_aprobacion(cierre))
        cierre.correo_at = ahora
        await db.commit()
        logger.info("leaderboard %s: correo de cierre enviado (%d en el top)", cierre.mes, len(top))
