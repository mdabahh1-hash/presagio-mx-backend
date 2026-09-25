"""Leaderboard mensual con premios al top 3.

Ganancia del mes = Σ de los trades hechos en el mes calendario (CDMX) de
[valor(trade) − costo]. Solo hay compras, así que cada trade conserva sus
acciones hasta resolver:
  resuelto  → shares si ganó, 0 si no (lmsr.posicion_gana)
  cancelado → su costo (el reembolso lo devuelve: ganancia 0)
  sin resolver → min(shares × precio LMSR, costo): una pérdida abierta resta,
                 una ganancia abierta no suma hasta resolver (nadie sube puestos
                 inflando el precio de un mercado poco líquido al cierre)
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
from app.models.leaderboard_mes import LeaderboardAviso, LeaderboardMes, LeaderboardMesFila
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
INICIO = date(2026, 10, 1)  # primer mes con premios: octubre 2026

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
    # Sin resolver: marca LMSR (igual que `users._enrich_positions`), topada en el costo.
    if multi:
        if not q_multi or t.outcome_key not in q_multi:
            return t.cost
        p = lmsr.outcome_price(q_multi, m.b, t.outcome_key)
        marca = t.shares * (1.0 - p if t.side == TradeSide.NO else p)
    else:
        p_yes = lmsr.yes_price(m.q_yes, m.q_no, m.b)
        marca = t.shares * (p_yes if (t.outcome_key or side) == "YES" else 1.0 - p_yes)
    return min(marca, t.cost)


_REALIZADOS = (*_RESUELTOS, MarketStatus.RESOLVED, MarketStatus.CANCELLED)


async def realizados(db: AsyncSession, user_ids: list[int]) -> list[tuple[int, date, float]]:
    """(user_id, día CDMX en que se resolvió, ganancia) de cada trade en un mercado
    resuelto o cancelado. Es el P&L del perfil, «Siguiendo» y el leaderboard
    histórico: solo trades, sin bonos, referidos ni los 10k de registro. Apostar
    no lo mueve; resolver sí."""
    if not user_ids:
        return []
    rows = (await db.execute(
        select(Trade, Market).join(Market, Market.id == Trade.market_id)
        .where(Trade.user_id.in_(user_ids), Market.status.in_(_REALIZADOS))
    )).all()
    return [
        (t.user_id, (m.resolved_at or m.ends_at).astimezone(MX).date(), valor_trade(t, m, None) - t.cost)
        for t, m in rows
    ]


async def ganancia_realizada(db: AsyncSession, user_ids: list[int]) -> dict[int, float]:
    g: dict[int, float] = {}
    for uid, _, v in await realizados(db, user_ids):
        g[uid] = g.get(uid, 0.0) + v
    return g


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


async def trofeos_de(db: AsyncSession, user_ids: list[int]) -> dict[int, list[dict]]:
    """{user_id: [{mes, rank}]} de los podios en meses publicados, del más reciente al más viejo."""
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(LeaderboardMesFila.user_id, LeaderboardMesFila.mes, LeaderboardMesFila.rank)
        .join(LeaderboardMes, LeaderboardMes.mes == LeaderboardMesFila.mes)
        .where(LeaderboardMes.status == "approved", LeaderboardMesFila.rank <= PREMIADOS,
               LeaderboardMesFila.user_id.in_(user_ids))
        .order_by(LeaderboardMesFila.mes.desc())
    )).all()
    out: dict[int, list[dict]] = {}
    for uid, mes, rank in rows:
        out.setdefault(uid, []).append({"mes": mes, "rank": rank})
    return out


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
    if anterior < INICIO:
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


# ── avisos de competencia ────────────────────────────────────────────────────

AVISO_ULTIMOS = timedelta(hours=72)


def tipo_aviso(ahora: datetime) -> str | None:
    """`ultimos` en las 72 h antes del cierre; `semana-<n>` los lunes desde las 09:00 CDMX."""
    mx = ahora.astimezone(MX)
    if mes_de(ahora) < INICIO:
        return None
    if limites(mes_de(ahora))[1] - ahora <= AVISO_ULTIMOS:
        return "ultimos"
    if mx.weekday() == 0 and mx.hour >= 9:
        return f"semana-{mx.isocalendar().week}"
    return None


async def avisos_competencia(ahora: datetime | None = None) -> int:
    """Idempotente (tabla `leaderboard_avisos`); lo llama el loop de mantenimiento.
    Manda a quien operó este mes su lugar o lo que le falta. Devuelve cuántos mandó."""
    import app.database as app_db
    from app.services.email import send_competencia_email

    ahora = ahora or datetime.now(timezone.utc)
    tipo = tipo_aviso(ahora)
    if tipo is None:
        return 0
    mes = mes_de(ahora)
    fin = limites(mes)[1]
    enviados = 0
    async with app_db.AsyncSessionLocal() as db:
        ya = set((await db.execute(select(LeaderboardAviso.user_id).where(
            LeaderboardAviso.mes == clave(mes), LeaderboardAviso.tipo == tipo))).scalars())
        filas = await ranking_mes(db, mes)
        podio = [f.ganancia for f in filas if f.rank and f.rank <= PREMIADOS]
        umbral = podio[-1] if len(podio) >= PREMIADOS else None
        for f in filas:
            u = f.user
            if u.id in ya or not u.email or not u.email_notifications or u.email == ADMIN_EMAIL:
                continue
            para_podio = None
            if f.elegible and f.rank and f.rank > PREMIADOS and umbral is not None:
                para_podio = max(0.0, umbral - f.ganancia)
            try:
                await send_competencia_email(
                    u.email, u.display_name, ultimos=tipo == "ultimos", dias=max(0, (fin - ahora).days),
                    rank=f.rank, ganancia=f.ganancia, para_podio=para_podio,
                    faltan_predicciones=max(0, MIN_PREDICCIONES - f.n_trades),
                    faltan_mercados=max(0, MIN_MERCADOS - f.n_mercados),
                )
            except Exception:  # noqa: BLE001  (se reintenta en la siguiente vuelta)
                logger.exception("leaderboard: aviso %s a %s falló", tipo, u.id)
                continue
            db.add(LeaderboardAviso(user_id=u.id, mes=clave(mes), tipo=tipo))
            await db.commit()
            enviados += 1
    if enviados:
        logger.info("leaderboard %s: %d avisos %s", clave(mes), enviados, tipo)
    return enviados
