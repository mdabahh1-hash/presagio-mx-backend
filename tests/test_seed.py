"""Tests del sembrador de arranque (app/services/seed.py).

seed_markets() corre en cada boot (lifespan de app/main.py). Debe ser SOLO
bootstrap de BD vacía: si re-insertara ids faltantes, un mercado borrado a
propósito (cleanup-mercados-vencidos-sin-predicciones-*.py) resucitaría en el
siguiente deploy.
"""
import pytest
from sqlalchemy import func, select

import app.database as app_db
import app.services.seed as seed_module
from app.models.market import Market
from app.services.seed import JUNE_2026_MARKETS, SEED_MARKETS, seed_markets


@pytest.fixture(autouse=True)
def _seed_uses_test_db(monkeypatch):
    # seed.py liga AsyncSessionLocal en import; apuntamos al sessionmaker de
    # test sin depender del orden de imports de conftest.
    monkeypatch.setattr(seed_module, "AsyncSessionLocal", app_db.AsyncSessionLocal)


async def _count_markets(db) -> int:
    return (await db.execute(select(func.count()).select_from(Market))).scalar_one()


async def test_seed_markets_skips_when_markets_exist(db, make_binary_market):
    await make_binary_market("m1")
    await seed_markets()
    assert await _count_markets(db) == 1


async def test_seed_markets_bootstraps_empty_db(db):
    await seed_markets()
    assert await _count_markets(db) == len(JUNE_2026_MARKETS) + len(SEED_MARKETS)
