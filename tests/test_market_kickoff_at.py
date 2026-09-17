"""markets.kickoff_at (hora del evento): sale en list/detail, el atajo `tipo: partido` la
deriva del kickoff, un multi con kind: partido la exige, el runner la escribe, el PATCH
admin la mueve junto con ends_at en los partidos y el backfill de migrate_columns la
copia de ends_at en lo ya sembrado."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.database import migrate_columns
from app.models.market import Market, MarketCategory, MarketStatus
from seeds.runner import sembrar
from seeds.schema import SchemaError, cargar_texto
from tests.conftest import auth_headers

CONTEXTO = (
    "Contexto de prueba con hechos estables y suficiente longitud para pasar el mínimo "
    "de ciento veinte caracteres que exige el esquema del sembrador, igual que market_content."
)
UTC = timezone.utc

PARTIDO_YAML = f"""
---
tipo: partido
id: mx-america-guadalajara-j9-a30
competencia: Liga MX
local: América
visitante: Guadalajara
kickoff: 2030-09-20T03:15:00Z
pct: [45, 27, 28]
ventana: la Jornada 9 del Apertura 2030 (18 al 20 de septiembre)
context: |
  {CONTEXTO}
"""


def _multi_nfl(kickoff_line: str = "", category: str = "DEPORTES") -> str:
    return f"""
---
tipo: multi
id: nfl-chiefs-colts-s2-2030
question: ¿Quién gana Chiefs vs Colts?
description: Ganador del partido de la Semana 2.
category: {category}
subcategory: NFL
kind: partido
resolution_criteria: Resultado oficial de NFL.com, incluido el tiempo extra.
resolution_source_url: https://www.nfl.com/scores/
rules: |
  {CONTEXTO} {CONTEXTO}
context: |
  {CONTEXTO}
ends_at: 2030-09-21T00:20:00Z
{kickoff_line}
outcomes:
  - {{key: chiefs, label: Chiefs, pct: 55}}
  - {{key: colts, label: Colts, pct: 45}}
"""


def _market(mid: str, kind: str | None, sujeto: dict | None = None, kickoff_at: datetime | None = None) -> Market:
    return Market(
        id=mid, question=f"¿Quién gana {mid}?", description="Mercado de prueba",
        category=MarketCategory.DEPORTES, subcategory="Liga MX", kind=kind, sujeto=sujeto,
        resolution_criteria="Prueba", ends_at=datetime.now(UTC) + timedelta(days=3), kickoff_at=kickoff_at,
        b=1000.0, q_yes=0.0, q_no=0.0, yes_price=50.0, status=MarketStatus.OPEN, market_type="binary",
    )


def test_partido_deriva_kickoff_at_del_kickoff():
    specs, _ = cargar_texto(PARTIDO_YAML)
    [s] = specs
    assert s.kind == "partido"
    assert s.kickoff_at == s.ends_at == datetime(2030, 9, 20, 3, 15, tzinfo=UTC)


def test_multi_con_kind_partido_exige_kickoff_at_coherente():
    with pytest.raises(SchemaError) as exc:
        cargar_texto(_multi_nfl())
    assert "requiere kickoff_at" in "\n".join(exc.value.errores)

    specs, _ = cargar_texto(_multi_nfl("kickoff_at: 2030-09-21T00:20:00Z"))
    assert specs[0].kickoff_at == datetime(2030, 9, 21, 0, 20, tzinfo=UTC)

    with pytest.raises(SchemaError) as exc:
        cargar_texto(_multi_nfl("kickoff_at: 2030-09-22T00:00:00Z"))
    assert "posterior a ends_at" in "\n".join(exc.value.errores)

    with pytest.raises(SchemaError) as exc:
        cargar_texto(_multi_nfl("kickoff_at: 2030-09-21T00:20:00Z", category="TECH"))
    assert "kickoff_at solo va en DEPORTES" in "\n".join(exc.value.errores)


@pytest.mark.asyncio
async def test_runner_escribe_kickoff_at(db):
    specs, _ = cargar_texto(PARTIDO_YAML)
    await sembrar(specs, db, apply=True, log=lambda *_: None)
    m = (await db.execute(select(Market).where(Market.id == specs[0].id))).scalar_one()
    assert m.kickoff_at == m.ends_at == datetime(2030, 9, 20, 3, 15, tzinfo=UTC)


@pytest.mark.asyncio
async def test_kickoff_at_sale_en_list_y_detail(client, db):
    hora = datetime(2030, 9, 20, 3, 15, tzinfo=UTC)
    db.add_all([_market("k-con", "partido", kickoff_at=hora), _market("k-sin", None)])
    await db.commit()

    listing = await client.get("/api/markets", params={"subcategory": "Liga MX"})
    por_id = {r["id"]: r["kickoff_at"] for r in listing.json()}
    assert por_id["k-con"].startswith("2030-09-20T03:15:00")
    assert por_id["k-sin"] is None
    detail = await client.get("/api/markets/k-con")
    assert detail.json()["kickoff_at"].startswith("2030-09-20T03:15:00")


@pytest.mark.asyncio
async def test_patch_mueve_kickoff_at_con_ends_at_solo_en_partidos(client, db, make_user):
    admin = await make_user("admin-kickoff")
    admin.email = "mdabahh@atid.edu.mx"
    partido = _market("k-partido", "partido")
    partido.kickoff_at = partido.ends_at
    otro = _market("k-otro", None)
    db.add_all([partido, otro])
    await db.commit()
    headers = auth_headers(admin)
    nueva = (datetime.now(UTC) + timedelta(days=10)).replace(microsecond=0)

    resp = await client.patch("/api/admin/markets/k-partido", json={"ends_at": nueva.isoformat()}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cambios"] == ["ends_at", "kickoff_at"]
    body = (await client.get("/api/markets/k-partido")).json()
    assert body["ends_at"] == body["kickoff_at"]
    assert datetime.fromisoformat(body["kickoff_at"]) == nueva

    resp = await client.patch("/api/admin/markets/k-otro", json={"ends_at": nueva.isoformat()}, headers=headers)
    assert resp.json()["cambios"] == ["ends_at"]
    assert (await client.get("/api/markets/k-otro")).json()["kickoff_at"] is None

    explicita = (nueva - timedelta(hours=2)).isoformat()
    resp = await client.patch("/api/admin/markets/k-otro", json={"kickoff_at": explicita}, headers=headers)
    assert resp.json()["cambios"] == ["kickoff_at"]
    assert datetime.fromisoformat((await client.get("/api/markets/k-otro")).json()["kickoff_at"]) == nueva - timedelta(hours=2)


@pytest.mark.asyncio
async def test_backfill_de_migrate_columns_copia_ends_at_en_partidos(db):
    alcance_partido = {"jugador": "X", "equipo": "A", "rival": "B", "alcance": "partido", "ids": {"espn": "1"}}
    alcance_temporada = {"jugador": "X", "equipo": "A", "rival": "B", "alcance": "temporada", "ids": {"espn": "1"}}
    db.add_all([
        _market("bf-partido", "partido"),
        _market("bf-acc-partido", "accesorio", sujeto=alcance_partido),
        _market("bf-acc-temporada", "accesorio", sujeto=alcance_temporada),
        _market("bf-sin-kind", None),
    ])
    await db.commit()

    await migrate_columns()  # idempotente: corre en cada boot de prod

    res = await db.execute(select(Market).where(Market.id.like("bf-%")).execution_options(populate_existing=True))
    por_id = {m.id: m for m in res.scalars().all()}
    assert por_id["bf-partido"].kickoff_at == por_id["bf-partido"].ends_at
    assert por_id["bf-acc-partido"].kickoff_at == por_id["bf-acc-partido"].ends_at
    assert por_id["bf-acc-temporada"].kickoff_at is None
    assert por_id["bf-sin-kind"].kickoff_at is None
