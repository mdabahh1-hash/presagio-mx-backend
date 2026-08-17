"""Test bootstrap.

CRITICAL ORDERING: app/config.py builds Settings() and app/database.py builds
the engine at import time, so DATABASE_URL and SECRET_KEY must be set BEFORE
any `app.*` import. Keep the os.environ lines at the very top.

Tests run against a scratch local Postgres DB (veredikt_test) that is dropped
and recreated once per test run; tables are truncated between tests.
"""
import os
import asyncio
from datetime import datetime, timedelta, timezone

TEST_DB = "veredikt_test"
TEST_DB_URL = f"postgresql+asyncpg://markdabah@localhost:5432/{TEST_DB}"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"

import asyncpg  # noqa: E402
import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker  # noqa: E402


def _bootstrap_database() -> None:
    """Drop + recreate the scratch DB (connects to the maintenance DB)."""
    async def run():
        conn = await asyncpg.connect(host="localhost", user="markdabah", database="postgres")
        await conn.execute(f'DROP DATABASE IF EXISTS {TEST_DB}')
        await conn.execute(f'CREATE DATABASE {TEST_DB}')
        await conn.close()
    asyncio.run(run())


_bootstrap_database()

# Import the app only AFTER env vars + scratch DB exist.
import app.models  # noqa: E402,F401  (registers all models on Base.metadata)
import app.database as app_db  # noqa: E402
from app.database import Base  # noqa: E402

# Replace the app engine with a NullPool one: pytest-asyncio gives each test its
# own event loop, and pooled asyncpg connections are bound to the loop that
# created them. NullPool opens a fresh connection per checkout, so nothing
# leaks across loops. get_db() reads the module global at call time, so
# patching app_db.AsyncSessionLocal is enough for the API under test.
app_db.engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
app_db.AsyncSessionLocal = async_sessionmaker(app_db.engine, class_=AsyncSession, expire_on_commit=False)


def _create_schema() -> None:
    async def run():
        async with app_db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await app_db.engine.dispose()
    asyncio.run(run())


_create_schema()

from app.main import app  # noqa: E402  (ASGITransport does not run the lifespan: no seeds, no maintenance loop)
from app.models.market import Market, MarketCategory, MarketStatus  # noqa: E402
from app.models.outcome import Outcome  # noqa: E402
from app.models.user import User  # noqa: E402
from app.core.auth import create_access_token  # noqa: E402
from app.core import lmsr  # noqa: E402

ALL_TABLES = (
    "points_ledger, follows, price_history, comments, positions, trades, market_outcomes, markets, users"
)


@pytest_asyncio.fixture(autouse=True)
async def _clean_db():
    yield
    async with app_db.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {ALL_TABLES} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db():
    async with app_db.AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def make_user(db):
    async def _make(username: str = "tester", points: float = 100_000.0) -> User:
        u = User(
            email=f"{username}@test.local",
            username=username,
            display_name=username.replace("_", " ").title(),
            email_verified=True,
            points=points,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u
    return _make


def auth_headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


@pytest_asyncio.fixture
async def make_binary_market(db):
    """Factory for a fresh OPEN binary market.

    initial_yes=None → balanced 50/50 (q_yes=q_no=0). Otherwise the opening
    price is derived exactly like production seeds do: lmsr.init_q_for_price.
    """
    async def _make(
        market_id: str,
        b: float = 100.0,
        initial_yes: float | None = None,
    ) -> Market:
        if initial_yes is None:
            q_yes, q_no = 0.0, 0.0
        else:
            q_yes, q_no = lmsr.init_q_for_price(initial_yes, b)
        m = Market(
            id=market_id,
            question=f"¿Test {market_id}?",
            description="Mercado de prueba",
            category=MarketCategory.TECH,
            resolution_criteria="Prueba",
            ends_at=datetime.now(timezone.utc) + timedelta(days=30),
            b=b,
            q_yes=q_yes,
            q_no=q_no,
            yes_price=lmsr.yes_price_pct(q_yes, q_no, b),
            status=MarketStatus.OPEN,
            market_type="binary",
        )
        db.add(m)
        await db.commit()
        await db.refresh(m)
        return m
    return _make


@pytest_asyncio.fixture
async def make_multi_market(db):
    """Factory for a fresh OPEN multi-outcome market with equal-priced outcomes."""
    async def _make(
        market_id: str,
        outcome_keys: tuple[str, ...] = ("A", "B", "C"),
        b: float = 100.0,
    ) -> Market:
        m = Market(
            id=market_id,
            question=f"¿Test multi {market_id}?",
            description="Mercado multi de prueba",
            category=MarketCategory.TECH,
            resolution_criteria="Prueba",
            ends_at=datetime.now(timezone.utc) + timedelta(days=30),
            b=b,
            q_yes=0.0,
            q_no=0.0,
            yes_price=round(100.0 / len(outcome_keys), 2),
            status=MarketStatus.OPEN,
            market_type="multi",
        )
        db.add(m)
        prices = lmsr.prices_multi({k: 0.0 for k in outcome_keys}, b)
        for k in outcome_keys:
            db.add(Outcome(market_id=market_id, outcome_key=k, label=f"Opción {k}", q=0.0, price=prices[k]))
        await db.commit()
        await db.refresh(m)
        return m
    return _make
