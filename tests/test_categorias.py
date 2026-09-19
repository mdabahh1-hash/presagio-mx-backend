"""GET /api/markets/categorias: categorías con mercados activos y su conteo. Cuenta
OPEN + PENDING_RESOLUTION (el mismo `active` de la lista); una categoría cuyos mercados
están todos resueltos o cancelados no aparece."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Market, MarketCategory, MarketStatus


def _market(mid: str, category: MarketCategory, status: MarketStatus = MarketStatus.OPEN) -> Market:
    return Market(
        id=mid, question=f"¿Test {mid}?", description="Mercado de prueba", category=category,
        resolution_criteria="Prueba", ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        b=1000.0, q_yes=0.0, q_no=0.0, yes_price=50.0, status=status, market_type="binary",
    )


@pytest.mark.asyncio
async def test_categorias_cuenta_activos(client, db):
    db.add_all([
        _market("cat-tech-1", MarketCategory.TECH),
        _market("cat-tech-2", MarketCategory.TECH, MarketStatus.RESOLVED_YES),        # no cuenta
        _market("cat-clima-pend", MarketCategory.CLIMA, MarketStatus.PENDING_RESOLUTION),  # sí cuenta
        _market("cat-mex-canc", MarketCategory.MEXICO, MarketStatus.CANCELLED),        # categoría fuera
    ])
    await db.commit()
    r = await client.get("/api/markets/categorias")
    assert r.status_code == 200
    assert sorted(r.json(), key=lambda c: c["categoria"]) == [
        {"categoria": "Clima", "activos": 1},
        {"categoria": "Tech", "activos": 1},
    ]


@pytest.mark.asyncio
async def test_categorias_vacio(client):
    r = await client.get("/api/markets/categorias")
    assert r.status_code == 200 and r.json() == []
