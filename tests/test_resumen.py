"""GET /api/markets/resumen?category=…: agregados por subcategoría para la landing de una
categoría (riel de ligas y "Volumen por liga" de Deportes)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.market import Market, MarketCategory, MarketStatus
from app.models.trade import Trade


def _market(mid: str, sub: str | None, volume: float, status: MarketStatus = MarketStatus.OPEN,
            category: MarketCategory = MarketCategory.DEPORTES) -> Market:
    return Market(
        id=mid, question=f"¿Test {mid}?", description="Mercado de prueba", category=category,
        subcategory=sub, resolution_criteria="Prueba",
        ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        b=1000.0, q_yes=0.0, q_no=0.0, yes_price=50.0, volume=volume, num_trades=1,
        status=status, market_type="binary",
    )


def _trade(user_id: int, mid: str, cost: float, dias_atras: float) -> Trade:
    return Trade(user_id=user_id, market_id=mid, side="YES", shares=1.0, cost=cost,
                 price_before=50.0, price_after=51.0,
                 created_at=datetime.now(timezone.utc) - timedelta(days=dias_atras))


@pytest.mark.asyncio
async def test_resumen_agrupa_por_subcategoria(client, db, make_user):
    u = await make_user("resumen-user")
    db.add_all([
        _market("res-mx-1", "Liga MX", 100.0),
        _market("res-mx-2", "Liga MX", 50.0),
        _market("res-nfl-1", "NFL", 300.0),
        _market("res-nfl-res", "NFL", 1000.0, status=MarketStatus.RESOLVED_YES),   # cuenta en volumen, no en abiertos
        _market("res-sin-sub", None, 5.0),                                          # totales sí, lista no
        _market("res-pol", "Elecciones", 999.0, category=MarketCategory.POLITICA_MX),  # otra categoría
    ])
    await db.commit()
    db.add_all([
        _trade(u.id, "res-mx-1", 40.0, 1),      # en ventana
        _trade(u.id, "res-mx-2", 10.0, 6.5),    # en ventana
        _trade(u.id, "res-nfl-1", 70.0, 10),    # fuera de la ventana de 7 días
        _trade(u.id, "res-sin-sub", 5.0, 1),    # sin subcategoría: solo al total
    ])
    await db.commit()

    resp = await client.get("/api/markets/resumen", params={"category": "Deportes"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["categoria"] == "Deportes"
    assert body["abiertos"] == 4
    assert body["volumen_total"] == 1455.0
    assert body["volumen_7d"] == 55.0
    assert [s["subcategory"] for s in body["subcategorias"]] == ["NFL", "Liga MX"]  # por volumen total
    nfl, mx = body["subcategorias"]
    assert (nfl["abiertos"], nfl["volumen_total"], nfl["volumen_7d"]) == (1, 1300.0, 0.0)
    assert (mx["abiertos"], mx["volumen_total"], mx["volumen_7d"]) == (2, 150.0, 50.0)


@pytest.mark.asyncio
async def test_resumen_categoria_vacia_y_parametro_obligatorio(client):
    resp = await client.get("/api/markets/resumen", params={"category": "Clima"})
    assert resp.status_code == 200
    assert resp.json() == {"categoria": "Clima", "abiertos": 0, "volumen_total": 0.0, "volumen_7d": 0.0, "subcategorias": []}

    assert (await client.get("/api/markets/resumen")).status_code == 422
    assert (await client.get("/api/markets/resumen", params={"category": "Nada"})).status_code == 422
