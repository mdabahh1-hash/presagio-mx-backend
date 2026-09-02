"""markets.image_url: opcional, se expone en list/detail y se acepta al crear."""
import pytest
from datetime import datetime, timedelta, timezone

from app.models.market import Market, MarketCategory, MarketStatus


@pytest.mark.asyncio
async def test_image_url_defaults_to_null(client, make_binary_market):
    m = await make_binary_market("img-none")
    assert m.image_url is None
    resp = await client.get(f"/api/markets/{m.id}")
    assert resp.status_code == 200
    assert resp.json()["image_url"] is None


@pytest.mark.asyncio
async def test_image_url_roundtrips(client, db):
    m = Market(
        id="img-set",
        question="¿Test imagen?",
        description="Mercado con imagen",
        category=MarketCategory.DEPORTES,
        subcategory="Liga MX",
        resolution_criteria="Prueba",
        image_url="/img/markets/sub/liga-mx.svg",
        ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        b=1000.0, q_yes=0.0, q_no=0.0, yes_price=50.0,
        status=MarketStatus.OPEN, market_type="binary",
    )
    db.add(m)
    await db.commit()

    detail = await client.get("/api/markets/img-set")
    assert detail.json()["image_url"] == "/img/markets/sub/liga-mx.svg"

    listing = await client.get("/api/markets", params={"subcategory": "Liga MX"})
    assert listing.status_code == 200
    by_id = {row["id"]: row for row in listing.json()}
    assert by_id["img-set"]["image_url"] == "/img/markets/sub/liga-mx.svg"
