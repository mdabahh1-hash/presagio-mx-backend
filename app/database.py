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
    """Add new enum values to existing PostgreSQL ENUM types (idempotent)."""
    new_status_values = ["pending_resolution"]
    new_category_values = ["Mundial 2026", "Crypto", "Mercados Globales", "México"]
    async with engine.begin() as conn:
        for v in new_status_values:
            await conn.execute(
                __import__("sqlalchemy", fromlist=["text"]).text(
                    f"ALTER TYPE marketstatus ADD VALUE IF NOT EXISTS '{v}'"
                )
            )
        for v in new_category_values:
            await conn.execute(
                __import__("sqlalchemy", fromlist=["text"]).text(
                    f"ALTER TYPE marketcategory ADD VALUE IF NOT EXISTS '{v}'"
                )
            )
