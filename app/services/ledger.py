"""Helper to append entries to the points ledger.

Call `record(...)` inside the same transaction that mutates `user.points`, so
the ledger stays consistent with the balance (no extra commit here — the caller
commits). Summing `delta` over a window yields realized P&L for that window.
"""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.points_ledger import PointsLedger


def record(
    db: AsyncSession,
    user_id: int,
    delta: float,
    reason: str,
    created_at: datetime | None = None,
) -> None:
    if not delta:
        return
    entry = PointsLedger(user_id=user_id, delta=delta, reason=reason)
    if created_at is not None:
        entry.created_at = created_at
    db.add(entry)
