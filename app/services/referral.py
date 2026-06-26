"""Referral codes + reward crediting.

Reward model (anti-abuse): both inviter and invitee receive REFERRAL_BONUS PT,
but only once the invitee places their FIRST trade. `referral_credited_at` makes
the payout idempotent.
"""
import secrets
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.config import settings
from app.services import ledger

# Unambiguous alphabet (no 0/O/1/I/L) for friendlier share links.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_code(length: int = 7) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


async def _unique_code(db: AsyncSession) -> str:
    for _ in range(10):
        code = generate_code()
        exists = await db.execute(select(User.id).where(User.referral_code == code))
        if exists.scalar_one_or_none() is None:
            return code
    # Extremely unlikely fallback: longer code.
    return generate_code(10)


async def ensure_code(db: AsyncSession, user: User) -> str:
    """Assign a referral code to `user` if missing. Does not commit."""
    if not user.referral_code:
        user.referral_code = await _unique_code(db)
    return user.referral_code


async def resolve_referrer(db: AsyncSession, code: str | None, new_user_email: str) -> int | None:
    """Return the referrer's user id for a referral code, or None if invalid /
    self-referral. Call at signup to set `referred_by_id`."""
    if not code:
        return None
    res = await db.execute(select(User).where(User.referral_code == code.strip().upper()))
    referrer = res.scalar_one_or_none()
    if not referrer or referrer.email == new_user_email:
        return None
    return referrer.id


async def credit_referral(db: AsyncSession, user: User) -> bool:
    """Credit the referral bonus to inviter + invitee after the invitee's first
    trade. Idempotent. Does not commit — the caller's transaction does. Returns
    True if a payout happened."""
    if not user.referred_by_id or user.referral_credited_at is not None:
        return False

    res = await db.execute(
        select(User).where(User.id == user.referred_by_id).with_for_update()
    )
    referrer = res.scalar_one_or_none()
    if not referrer:
        # Referrer vanished — mark as handled so we don't retry every trade.
        user.referral_credited_at = datetime.now(timezone.utc)
        return False

    bonus = float(settings.REFERRAL_BONUS)
    referrer.points += bonus
    user.points += bonus
    ledger.record(db, referrer.id, bonus, "referral")
    ledger.record(db, user.id, bonus, "referral")
    user.referral_credited_at = datetime.now(timezone.utc)
    return True


async def assign_codes_to_all(db: AsyncSession) -> None:
    """Backfill referral codes for existing users that don't have one."""
    res = await db.execute(select(User).where(User.referral_code.is_(None)))
    users = res.scalars().all()
    if not users:
        return
    for u in users:
        u.referral_code = await _unique_code(db)
    await db.commit()
