"""GET /api/markets?sort=new: lo último sembrado primero; pending_resolution al final."""
import pytest
from datetime import datetime, timedelta, timezone

from app.models.market import Market, MarketCategory, MarketStatus


def _market(mid: str, created_days_ago: int, status: MarketStatus = MarketStatus.OPEN) -> Market:
    now = datetime.now(timezone.utc)
    return Market(
        id=mid,
        question=f"¿Test {mid}?",
        description="Mercado de prueba",
        category=MarketCategory.TECH,
        subcategory="sort-new",
        resolution_criteria="Prueba",
        ends_at=now + timedelta(days=30) if status == MarketStatus.OPEN else now - timedelta(days=1),
        b=1000.0, q_yes=0.0, q_no=0.0, yes_price=50.0,
        status=status, market_type="binary",
        created_at=now - timedelta(days=created_days_ago),
    )


@pytest.mark.asyncio
async def test_sort_new_orders_by_created_at_desc_with_pending_last(client, db):
    db.add(_market("new-viejo", 10))
    db.add(_market("new-reciente", 0))
    db.add(_market("new-medio", 3))
    db.add(_market("new-pendiente", 0, MarketStatus.PENDING_RESOLUTION))
    await db.commit()

    resp = await client.get("/api/markets", params={"sort": "new", "subcategory": "sort-new"})
    assert resp.status_code == 200
    assert [row["id"] for row in resp.json()] == ["new-reciente", "new-medio", "new-viejo", "new-pendiente"]
