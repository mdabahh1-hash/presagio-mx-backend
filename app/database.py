from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def migrate_enums() -> None:
    """Add new enum values to existing PostgreSQL ENUM types (idempotent).
    SQLAlchemy stores Python enum NAMES (e.g. MUNDIAL_2026), not values.
    """
    from sqlalchemy import text
    new_status_names = ["PENDING_RESOLUTION", "RESOLVED"]
    new_category_names = ["MUNDIAL_2026", "CRYPTO", "MERCADOS_GLOBALES", "MEXICO"]
    async with engine.begin() as conn:
        for v in new_status_names:
            await conn.execute(text(f"ALTER TYPE marketstatus ADD VALUE IF NOT EXISTS '{v}'"))
        for v in new_category_names:
            await conn.execute(text(f"ALTER TYPE marketcategory ADD VALUE IF NOT EXISTS '{v}'"))


async def migrate_columns() -> None:
    """Add new columns to existing tables (idempotent).

    `create_all` only creates missing tables, never adds columns to existing
    ones, and Railway starts with plain `uvicorn` (no `alembic upgrade`). So new
    columns on long-lived tables are guaranteed here with ADD COLUMN IF NOT EXISTS.
    """
    from sqlalchemy import text
    stmts = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(16)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_id INTEGER REFERENCES users(id)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_credited_at TIMESTAMPTZ",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_referral_code ON users (referral_code)",
    ]
    async with engine.begin() as conn:
        for s in stmts:
            await conn.execute(text(s))
