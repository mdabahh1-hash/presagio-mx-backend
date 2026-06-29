"""Periodic market maintenance: closing-soon notices, auto-close, admin reminders.

Runs at startup and on a fixed interval (see app/main.py). One DB session per run.
Idempotency is guarded by Market.closing_notified_at / Market.resolution_reminded_at
so emails are sent at most once per market.
"""
import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.market import Market, MarketStatus
from app.models.position import Position
from app.models.user import User
from app.services.email import send_closing_soon_email, send_admin_resolution_reminder

# How far ahead of close we warn open-position holders.
CLOSING_SOON_WINDOW = timedelta(hours=24)


async def _notify_closing_soon(db: AsyncSession, now: datetime) -> None:
    """Email open-position holders for markets closing within the window."""
    window_end = now + CLOSING_SOON_WINDOW
    res = await db.execute(
        select(Market).where(
            Market.status == MarketStatus.OPEN,
            Market.ends_at > now,
            Market.ends_at <= window_end,
            Market.closing_notified_at.is_(None),
        )
    )
    markets = res.scalars().all()
    for m in markets:
        holders = await db.execute(
            select(User.email, User.display_name)
            .join(Position, Position.user_id == User.id)
            .where(
                Position.market_id == m.id,
                Position.shares > 0,
                User.email_notifications.is_(True),
                User.email.isnot(None),
            )
            .distinct()
        )
        for email, display_name in holders.all():
            asyncio.create_task(
                send_closing_soon_email(email, display_name, m.question, m.ends_at, m.id)
            )
        # Mark even when there were no holders, so we don't re-scan this market.
        m.closing_notified_at = now


async def _close_expired(db: AsyncSession, now: datetime) -> None:
    """Flip OPEN markets past their end date to PENDING_RESOLUTION."""
    res = await db.execute(
        select(Market).where(Market.status == MarketStatus.OPEN, Market.ends_at < now)
    )
    for m in res.scalars().all():
        m.status = MarketStatus.PENDING_RESOLUTION


async def _remind_admin(db: AsyncSession, now: datetime) -> None:
    """Email the admin a digest of markets that closed and await resolution."""
    res = await db.execute(
        select(Market).where(
            Market.status == MarketStatus.PENDING_RESOLUTION,
            Market.resolution_reminded_at.is_(None),
        )
    )
    pending = res.scalars().all()
    if not pending:
        return
    digest = [(m.id, m.question, m.ends_at) for m in pending]
    asyncio.create_task(send_admin_resolution_reminder(digest))
    for m in pending:
        m.resolution_reminded_at = now


async def run_market_maintenance() -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        # Order matters: warn before closing (so a just-expired market isn't
        # warned), then close, then remind admin about the newly-pending ones.
        await _notify_closing_soon(db, now)
        await _close_expired(db, now)
        await _remind_admin(db, now)
        await db.commit()
