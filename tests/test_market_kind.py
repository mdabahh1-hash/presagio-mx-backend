"""markets.kind ('partido' | 'accesorio'): opcional, se expone en list/detail y filtra con ?kind=."""
import pytest
from datetime import datetime, timedelta, timezone

from app.models.market import Market, MarketCategory, MarketStatus


def _market(mid: str, kind: str | None) -> Market:
    return Market(
        id=mid,
        question=f"¿Test {mid}?",
        description="Mercado de prueba",
        category=MarketCategory.DEPORTES,
        subcategory="Liga MX",
        kind=kind,
        resolution_criteria="Prueba",
        ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        b=1000.0, q_yes=0.0, q_no=0.0, yes_price=50.0,
        status=MarketStatus.OPEN, market_type="binary",
    )


@pytest.mark.asyncio
async def test_kind_defaults_to_null(client, make_binary_market):
    m = await make_binary_market("kind-none")
    assert m.kind is None
    resp = await client.get(f"/api/markets/{m.id}")
    assert resp.status_code == 200
    assert resp.json()["kind"] is None


@pytest.mark.asyncio
async def test_kind_filter_and_roundtrip(client, db):
    db.add(_market("kind-partido", "partido"))
    db.add(_market("kind-accesorio", "accesorio"))
    await db.commit()

    listing = await client.get("/api/markets", params={"subcategory": "Liga MX"})
    assert listing.status_code == 200
    by_id = {row["id"]: row["kind"] for row in listing.json()}
    assert by_id["kind-partido"] == "partido"
    assert by_id["kind-accesorio"] == "accesorio"

    only = await client.get("/api/markets", params={"subcategory": "Liga MX", "kind": "partido"})
    assert only.status_code == 200
    assert [row["id"] for row in only.json()] == ["kind-partido"]


@pytest.mark.asyncio
async def test_kind_rejects_unknown_value(client):
    resp = await client.get("/api/markets", params={"kind": "bogus"})
    assert resp.status_code == 422
