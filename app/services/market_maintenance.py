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

# In-memory record of the last maintenance run, exposed for health monitoring.
# Resets to ran_at=None on restart — so a stale/None ran_at means the loop isn't
# ticking (e.g. the server slept). See GET /api/health/maintenance.
_LAST_RUN: dict = {
    "ran_at": None,
    "run_count": 0,
    "last_closing_emails": 0,
    "last_closed": 0,
    "last_admin_reminders": 0,
}


def get_maintenance_status() -> dict:
    return dict(_LAST_RUN)


async def _notify_closing_soon(db: AsyncSession, now: datetime) -> int:
    """Email open-position holders for markets closing within the window.
    Returns the number of closing-soon emails queued."""
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
    emails = 0
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
            emails += 1
        # Mark even when there were no holders, so we don't re-scan this market.
        m.closing_notified_at = now
    return emails


async def _close_expired(db: AsyncSession, now: datetime) -> int:
    """Flip OPEN markets past their end date to PENDING_RESOLUTION. Returns count."""
    res = await db.execute(
        select(Market).where(Market.status == MarketStatus.OPEN, Market.ends_at < now)
    )
    expired = res.scalars().all()
    for m in expired:
        m.status = MarketStatus.PENDING_RESOLUTION
    return len(expired)


async def _remind_admin(db: AsyncSession, now: datetime) -> int:
    """Email the admin a digest of markets that closed and await resolution.
    Returns the number of markets in the reminder."""
    res = await db.execute(
        select(Market).where(
            Market.status == MarketStatus.PENDING_RESOLUTION,
            Market.resolution_reminded_at.is_(None),
        )
    )
    pending = res.scalars().all()
    if not pending:
        return 0
    digest = [(m.id, m.question, m.ends_at) for m in pending]
    asyncio.create_task(send_admin_resolution_reminder(digest))
    for m in pending:
        m.resolution_reminded_at = now
    return len(pending)


async def run_market_maintenance() -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        # Order matters: warn before closing (so a just-expired market isn't
        # warned), then close, then remind admin about the newly-pending ones.
        closing_emails = await _notify_closing_soon(db, now)
        closed = await _close_expired(db, now)
        admin_reminders = await _remind_admin(db, now)
        await db.commit()

    _LAST_RUN.update(
        ran_at=now.isoformat(),
        run_count=_LAST_RUN["run_count"] + 1,
        last_closing_emails=closing_emails,
        last_closed=closed,
        last_admin_reminders=admin_reminders,
    )
