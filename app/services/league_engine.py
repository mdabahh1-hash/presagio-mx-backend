"""
Motor de Ligas Privadas: precio snapshot, seed de ciclos y resolución.

REGLA DURA: nada de aquí toca el trade path ni el AMM. Un pick de liga solo
LEE el precio marginal actual. No modifica q, no escribe en points_ledger
global, no crea trades.

El precio snapshot reusa exactamente los helpers LMSR que usa
GET /markets/{id}/quote (`lmsr.yes_price` / `lmsr.outcome_price`, sin size).
No hay matemática LMSR duplicada aquí.
"""
import secrets
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import lmsr
from app.models.league import (
    LeagueCycle,
    LeagueCycleMarket,
    LeagueCycleStanding,
    LeaguePrediction,
)
from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome

PAYOUT_CAP_MULT = Decimal("20")
INVITE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # sin caracteres ambiguos
PRICE_Q = Decimal("0.000001")

# Estados terminales de un mercado global (ya no cambia el resultado).
RESOLVED_STATUSES = (
    MarketStatus.RESOLVED_YES,
    MarketStatus.RESOLVED_NO,
    MarketStatus.RESOLVED,
    MarketStatus.CANCELLED,
)


def generate_invite_code(length: int = 8) -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(length))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_price(p: float) -> Decimal:
    """float (0-1) del motor LMSR → Decimal con 6 decimales."""
    return Decimal(str(p)).quantize(PRICE_Q, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- precio

async def snapshot_prices(db: AsyncSession, market: Market) -> dict:
    """
    Precios marginales ACTUALES del mercado, misma fuente que /quote.

    binario → {"yes": Decimal, "no": Decimal}
    multi   → {outcome.id: (Outcome, Decimal)}
    """
    if market.market_type == "multi":
        outcomes = (
            await db.execute(select(Outcome).where(Outcome.market_id == market.id))
        ).scalars().all()
        q_dict = {o.outcome_key: o.q for o in outcomes}
        return {
            o.id: (o, _to_price(lmsr.outcome_price(q_dict, market.b, o.outcome_key)))
            for o in outcomes
        }

    p_yes = _to_price(lmsr.yes_price(market.q_yes, market.q_no, market.b))
    return {"yes": p_yes, "no": Decimal("1") - p_yes}


async def get_snapshot_price(
    db: AsyncSession,
    market: Market,
    outcome_id: int | None,
    binary_side: str | None,
) -> Decimal:
    """
    Precio marginal ACTUAL del outcome elegido, como Decimal en (0, 1).
    Lanza ValueError si la selección no corresponde al tipo de mercado.
    """
    prices = await snapshot_prices(db, market)
    if market.market_type == "multi":
        if outcome_id is None or outcome_id not in prices:
            raise ValueError("Este mercado requiere un outcome_id válido")
        return prices[outcome_id][1]
    if binary_side not in ("yes", "no"):
        raise ValueError("Este mercado requiere binary_side 'yes' o 'no'")
    return prices[binary_side]


def compute_payout(stake: Decimal, price: Decimal) -> Decimal:
    """Payout si acierta: stake / price, con cap de 20x."""
    raw = stake / price
    capped = min(raw, stake * PAYOUT_CAP_MULT)
    return q2(capped)


# ---------------------------------------------------------------- seed

async def seed_cycle_markets(
    db: AsyncSession,
    cycle: LeagueCycle,
) -> int:
    """
    Siembra los mercados del ciclo filtrando por subcategory + ventana de
    cierre. Regresa cuántos mercados quedaron. Cero => el caller debe abortar
    con CYCLE_EMPTY y hacer rollback.
    """
    stmt = select(Market).where(
        Market.status == MarketStatus.OPEN,
        Market.ends_at >= cycle.starts_at,
        Market.ends_at <= cycle.ends_at,
    )
    if cycle.subcategory:
        stmt = stmt.where(Market.subcategory == cycle.subcategory)

    markets = (await db.execute(stmt)).scalars().all()
    for m in markets:
        db.add(LeagueCycleMarket(cycle_id=cycle.id, market_id=m.id))
    return len(markets)


async def create_standings_for_members(
    db: AsyncSession, cycle: LeagueCycle, user_ids: list[int]
) -> None:
    for uid in user_ids:
        db.add(
            LeagueCycleStanding(
                cycle_id=cycle.id, user_id=uid, balance=cycle.initial_stack
            )
        )


# ---------------------------------------------------------------- resolución

async def process_market_resolution_for_leagues(
    db: AsyncSession,
    market_id: str,
    winning_outcome_id: int | None,
    winning_binary_side: str | None,
    voided: bool = False,
) -> None:
    """
    Hook. Se llama desde el flujo admin de resolución de mercados, DESPUÉS
    de resolver el mercado global y dentro de la misma transacción.

    Paga/liquida todos los picks de liga abiertos de ese mercado y cierra
    los ciclos que hayan quedado completos.
    """
    preds = (
        (
            await db.execute(
                select(LeaguePrediction).where(
                    LeaguePrediction.market_id == market_id,
                    LeaguePrediction.status == "open",
                )
            )
        )
        .scalars()
        .all()
    )
    if not preds:
        return

    touched_cycles: set[int] = set()

    for p in preds:
        standing = (
            await db.execute(
                select(LeagueCycleStanding)
                .where(
                    LeagueCycleStanding.cycle_id == p.cycle_id,
                    LeagueCycleStanding.user_id == p.user_id,
                )
                .with_for_update()
            )
        ).scalar_one()

        if voided:
            p.status = "void"
            p.payout = q2(p.stake)
            standing.balance = q2(standing.balance + p.stake)
        else:
            won = (
                p.outcome_id is not None and p.outcome_id == winning_outcome_id
            ) or (
                p.binary_side is not None and p.binary_side == winning_binary_side
            )
            if won:
                p.status = "won"
                p.payout = compute_payout(p.stake, p.price_at_prediction)
                standing.balance = q2(standing.balance + p.payout)
            else:
                p.status = "lost"
                p.payout = Decimal("0.00")

        touched_cycles.add(p.cycle_id)

    for cycle_id in touched_cycles:
        await maybe_resolve_cycle(db, cycle_id)


async def maybe_resolve_cycle(db: AsyncSession, cycle_id: int) -> bool:
    """
    Si TODOS los mercados del ciclo ya están resueltos globalmente, cierra
    el ciclo, calcula final_rank por balance descendente (empates comparten
    rank) y marca resolved. Regresa True si lo resolvió.
    """
    cycle = (
        await db.execute(select(LeagueCycle).where(LeagueCycle.id == cycle_id))
    ).scalar_one()
    if cycle.status == "resolved":
        return False

    unresolved = (
        await db.execute(
            select(func.count())
            .select_from(LeagueCycleMarket)
            .join(Market, Market.id == LeagueCycleMarket.market_id)
            .where(
                LeagueCycleMarket.cycle_id == cycle_id,
                Market.status.notin_(RESOLVED_STATUSES),
            )
        )
    ).scalar_one()
    if unresolved > 0:
        if cycle.status == "open" and now_utc() > cycle.ends_at:
            cycle.status = "scoring"
        return False

    standings = (
        (
            await db.execute(
                select(LeagueCycleStanding)
                .where(LeagueCycleStanding.cycle_id == cycle_id)
                .order_by(LeagueCycleStanding.balance.desc())
            )
        )
        .scalars()
        .all()
    )

    rank = 0
    prev_balance: Decimal | None = None
    for i, s in enumerate(standings, start=1):
        if prev_balance is None or s.balance < prev_balance:
            rank = i
            prev_balance = s.balance
        s.final_rank = rank

    cycle.status = "resolved"
    cycle.resolved_at = now_utc()
    return True
