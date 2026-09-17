"""GET /api/markets/movers: mercados que más se movieron en N horas (página Noticias)."""
import pytest
from datetime import datetime, timedelta, timezone

from app.models.market import MarketStatus
from app.models.price_history import PriceHistory


def _fila(market_id: str, horas_atras: float, precio: float, key: str | None = None, vol: float = 0.0) -> PriceHistory:
    return PriceHistory(
        market_id=market_id, outcome_key=key, yes_price=precio, volume_snapshot=vol,
        recorded_at=datetime.now(timezone.utc) - timedelta(hours=horas_atras),
    )


@pytest.mark.asyncio
async def test_binario_cambio_desde_linea_base(client, db, make_binary_market):
    m = await make_binary_market("mov-bin")
    db.add(_fila(m.id, 30, 40.0, vol=100.0))   # línea base (antes de la ventana)
    db.add(_fila(m.id, 2, 60.0, vol=350.0))    # dentro de la ventana
    await db.commit()

    resp = await client.get("/api/markets/movers", params={"hours": 24})
    assert resp.status_code == 200
    [item] = [r for r in resp.json() if r["id"] == m.id]
    assert item["price_before"] == 40.0
    assert item["price"] == 60.0
    assert item["change"] == 20.0
    assert item["volume_delta"] == 250.0
    assert item["outcome_key"] is None and item["outcome_label"] is None
    assert [p["price"] for p in item["points"]] == [40.0, 60.0]

    # Con ventana de 1 h la fila de hace 2 h queda fuera → no aparece
    resp = await client.get("/api/markets/movers", params={"hours": 1})
    assert all(r["id"] != m.id for r in resp.json())


@pytest.mark.asyncio
async def test_multi_ignora_placeholder_y_elige_outcome_mayor(client, db, make_multi_market):
    m = await make_multi_market("mov-multi", ("A", "B"))
    db.add(_fila(m.id, 30, 0.0))               # placeholder del seed (key NULL): se ignora
    db.add(_fila(m.id, 3, 50.0, key="A"))
    db.add(_fila(m.id, 3, 50.0, key="B"))
    db.add(_fila(m.id, 1, 35.0, key="A"))
    db.add(_fila(m.id, 1, 65.0, key="B"))      # |cambio| igual; desempata el orden de inserción
    db.add(_fila(m.id, 0.5, 30.0, key="A"))    # A termina con -20, B con +15
    await db.commit()

    resp = await client.get("/api/markets/movers", params={"hours": 24})
    [item] = [r for r in resp.json() if r["id"] == m.id]
    assert item["outcome_key"] == "A"
    assert item["outcome_label"] == "Opción A"
    assert item["change"] == -20.0
    assert item["price_before"] == 50.0


@pytest.mark.asyncio
async def test_orden_filtros_y_limite(client, db, make_binary_market):
    grande = await make_binary_market("mov-grande")
    chico = await make_binary_market("mov-chico")
    quieto = await make_binary_market("mov-quieto")
    resuelto = await make_binary_market("mov-resuelto")
    resuelto.status = MarketStatus.RESOLVED_YES
    for mid, antes, ahora in ((grande.id, 50, 20), (chico.id, 50, 55), (quieto.id, 50, 50.5), (resuelto.id, 10, 90)):
        db.add(_fila(mid, 30, antes))
        db.add(_fila(mid, 2, ahora))
    await db.commit()

    resp = await client.get("/api/markets/movers", params={"hours": 24})
    ids = [r["id"] for r in resp.json()]
    assert ids.index(grande.id) < ids.index(chico.id)
    assert quieto.id not in ids      # |cambio| < 1 punto
    assert resuelto.id not in ids    # solo mercados activos

    resp = await client.get("/api/markets/movers", params={"hours": 24, "limit": 1})
    assert [r["id"] for r in resp.json()] == [grande.id]


@pytest.mark.asyncio
async def test_sin_linea_base_usa_primera_fila_de_la_ventana(client, db, make_binary_market):
    m = await make_binary_market("mov-nuevo")
    db.add(_fila(m.id, 5, 50.0))
    db.add(_fila(m.id, 1, 62.0))
    await db.commit()

    resp = await client.get("/api/markets/movers", params={"hours": 24})
    [item] = [r for r in resp.json() if r["id"] == m.id]
    assert item["price_before"] == 50.0 and item["change"] == 12.0


@pytest.mark.asyncio
async def test_filtra_por_categoria_y_subcategoria(client, db):
    from app.models.market import Market, MarketCategory

    def _dep(mid: str, sub: str) -> Market:
        return Market(
            id=mid, question=f"¿Test {mid}?", description="d", category=MarketCategory.DEPORTES,
            subcategory=sub, resolution_criteria="r",
            ends_at=datetime.now(timezone.utc) + timedelta(days=3),
            b=1000.0, q_yes=0.0, q_no=0.0, yes_price=50.0, status=MarketStatus.OPEN, market_type="binary",
        )

    db.add_all([_dep("mov-mx", "Liga MX"), _dep("mov-nfl", "NFL")])
    await db.commit()
    db.add_all([_fila("mov-mx", 30, 40.0), _fila("mov-mx", 2, 60.0), _fila("mov-nfl", 30, 50.0), _fila("mov-nfl", 2, 30.0)])
    await db.commit()

    todos = await client.get("/api/markets/movers", params={"hours": 24, "category": "Deportes"})
    assert {r["id"] for r in todos.json()} == {"mov-mx", "mov-nfl"}

    solo_nfl = await client.get("/api/markets/movers", params={"hours": 24, "subcategory": "NFL"})
    assert [r["id"] for r in solo_nfl.json()] == ["mov-nfl"]

    otra = await client.get("/api/markets/movers", params={"hours": 24, "category": "Tech"})
    assert all(r["id"] not in ("mov-mx", "mov-nfl") for r in otra.json())
