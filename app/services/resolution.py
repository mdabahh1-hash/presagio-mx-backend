"""Resolver un mercado: liquida posiciones, escribe el ledger, liquida ligas
privadas y notifica por correo. Reutilizable desde el endpoint admin y desde el
plan nocturno (sin FastAPI).

`resolve()` hace su propio `db.commit()`; ante error de dominio lanza
`ResolutionError` ANTES de tocar nada (el llamador debe hacer `db.rollback()`
si reutiliza la sesión).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import lmsr
from app.core.background import spawn
from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome
from app.models.position import Position
from app.models.user import User
from app.services import ledger
from app.services.email import send_market_cancelled_email, send_resolution_email
from app.services.league_engine import process_market_resolution_for_leagues


class ResolutionError(Exception):
    """Error de dominio con código SNAKE_CASE (el API lo traduce a HTTP)."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


async def resolve(
    db: AsyncSession,
    market_id: str,
    *,
    resolution: str | None = None,
    outcome_key: str | None = None,
) -> dict:
    """Resuelve un mercado binario (`resolution` YES/NO) o multi (`outcome_key`).

    Devuelve {"ok": True, "resolution": <YES|NO|outcome_key>, "positions_settled": n}.
    """
    result = await db.execute(select(Market).where(Market.id == market_id).with_for_update())
    market = result.scalar_one_or_none()
    if not market:
        raise ResolutionError("MARKET_NOT_FOUND", "Mercado no encontrado", status=404)
    if market.status not in (MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION, MarketStatus.CLOSED):
        raise ResolutionError("MARKET_ALREADY_RESOLVED", "Mercado ya resuelto o cancelado")

    if market.market_type == "multi":
        if not outcome_key:
            raise ResolutionError("OUTCOME_KEY_REQUIRED", "Especifica 'outcome_key' para mercados multi-resultado")
        outcomes_res = await db.execute(select(Outcome).where(Outcome.market_id == market_id))
        outcome_ids = {o.outcome_key: o.id for o in outcomes_res.scalars().all()}
        if outcome_key not in outcome_ids:
            raise ResolutionError("INVALID_OUTCOME_KEY", f"outcome_key inválido: {outcome_key}")
        etiqueta = outcome_key
        winning_outcome_id, winning_binary_side = outcome_ids[outcome_key], None

        def payout_de(pos: Position) -> tuple[float, bool]:
            gano = pos.outcome_key == outcome_key
            return (pos.shares if gano else 0.0), gano

        market.status = MarketStatus.RESOLVED
        market.resolved_outcome_key = outcome_key
    else:
        if not resolution:
            raise ResolutionError("RESOLUTION_REQUIRED", "Especifica 'resolution' (YES o NO) para mercados binarios")
        resolution = resolution.upper()
        if resolution not in ("YES", "NO"):
            raise ResolutionError("INVALID_RESOLUTION", "Resolución debe ser YES o NO")
        etiqueta = resolution
        winning_outcome_id, winning_binary_side = None, resolution.lower()

        def payout_de(pos: Position) -> tuple[float, bool]:
            side_val = pos.outcome_key or (pos.side.value if pos.side else "")
            payout = (
                lmsr.payout_if_yes(side_val, pos.shares)
                if resolution == "YES"
                else lmsr.payout_if_no(side_val, pos.shares)
            )
            gano = (resolution == "YES" and side_val == "YES") or (resolution == "NO" and side_val == "NO")
            return payout, gano

        market.status = MarketStatus.RESOLVED_YES if resolution == "YES" else MarketStatus.RESOLVED_NO

    market.resolved_at = datetime.now(timezone.utc)

    positions_result = await db.execute(
        select(Position).where(Position.market_id == market_id, Position.shares > 0)
    )
    positions = positions_result.scalars().all()
    notify: dict[int, dict] = {}

    for pos in positions:
        user_result = await db.execute(select(User).where(User.id == pos.user_id).with_for_update())
        user = user_result.scalar_one_or_none()
        if not user:
            continue
        payout, gano = payout_de(pos)
        user.points += payout
        ledger.record(db, user.id, payout, "payout")
        user.total_predictions += 1
        if gano:
            user.correct_predictions += 1
        pos.shares = 0
        if user.email and user.email_notifications:
            entry = notify.setdefault(
                user.id, {"email": user.email, "name": user.display_name, "payout": 0.0}
            )
            entry["payout"] += payout

    # Ligas privadas: liquidar picks de este mercado en la misma transacción.
    await process_market_resolution_for_leagues(
        db, market_id, winning_outcome_id=winning_outcome_id, winning_binary_side=winning_binary_side
    )
    await db.commit()

    question = market.question
    for entry in notify.values():
        spawn(send_resolution_email(entry["email"], entry["name"], question, entry["payout"] > 0, entry["payout"]))

    return {"ok": True, "resolution": etiqueta, "positions_settled": len(positions)}


async def cancel(db: AsyncSession, market_id: str) -> dict:
    """Cancela un mercado (aplazado fuera de ventana, jugador inactivo, empate
    en NFL…): devuelve a cada posición lo que pagó (`shares * avg_cost`) con
    fila de ledger "refund", anula los picks de ligas privadas (stake de vuelta)
    y avisa por correo. No cuenta como predicción acertada ni fallada.

    Devuelve {"ok": True, "resolution": "CANCELLED", "positions_refunded": n, "refunded": total}.
    """
    result = await db.execute(select(Market).where(Market.id == market_id).with_for_update())
    market = result.scalar_one_or_none()
    if not market:
        raise ResolutionError("MARKET_NOT_FOUND", "Mercado no encontrado", status=404)
    if market.status not in (MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION, MarketStatus.CLOSED):
        raise ResolutionError("MARKET_ALREADY_RESOLVED", "Mercado ya resuelto o cancelado")

    market.status = MarketStatus.CANCELLED
    market.resolved_at = datetime.now(timezone.utc)

    positions_result = await db.execute(
        select(Position).where(Position.market_id == market_id, Position.shares > 0)
    )
    positions = positions_result.scalars().all()
    notify: dict[int, dict] = {}
    total = 0.0
    for pos in positions:
        user_result = await db.execute(select(User).where(User.id == pos.user_id).with_for_update())
        user = user_result.scalar_one_or_none()
        if not user:
            continue
        refund = round(pos.shares * (pos.avg_cost or 0.0), 2)
        user.points += refund
        ledger.record(db, user.id, refund, "refund")
        pos.shares = 0
        total += refund
        if user.email and user.email_notifications:
            entry = notify.setdefault(user.id, {"email": user.email, "name": user.display_name, "refund": 0.0})
            entry["refund"] += refund

    await process_market_resolution_for_leagues(
        db, market_id, winning_outcome_id=None, winning_binary_side=None, voided=True
    )
    await db.commit()

    question = market.question
    for entry in notify.values():
        spawn(send_market_cancelled_email(entry["email"], entry["name"], question, entry["refund"]))

    return {"ok": True, "resolution": "CANCELLED", "positions_refunded": len(positions), "refunded": round(total, 2)}
