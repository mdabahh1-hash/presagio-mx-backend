from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.models.market import Market, MarketStatus, MarketCategory
from app.models.price_history import PriceHistory
from app.schemas.market import MarketList, MarketDetail, MarketCreate, PricePoint
from app.core.auth import get_current_user
from app.core import lmsr
from app.models.user import User

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=list[MarketList])
async def list_markets(
    category: MarketCategory | None = Query(None),
    status: MarketStatus = Query(MarketStatus.OPEN),
    trending: bool | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("volume"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Market).where(Market.status == status)
    if category:
        stmt = stmt.where(Market.category == category)
    if trending is not None:
        stmt = stmt.where(Market.trending == trending)
    if q:
        stmt = stmt.where(Market.question.ilike(f"%{q}%"))

    if sort == "volume":
        stmt = stmt.order_by(desc(Market.volume))
    elif sort == "liquidity":
        stmt = stmt.order_by(desc(Market.b))
    elif sort == "trending":
        stmt = stmt.order_by(desc(Market.trending), desc(Market.volume))
    elif sort == "ending":
        stmt = stmt.order_by(Market.ends_at)
    else:
        stmt = stmt.order_by(desc(Market.volume))

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{market_id}", response_model=MarketDetail)
async def get_market(market_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Market).where(Market.id == market_id))
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Mercado no encontrado")
    return market


@router.get("/{market_id}/history", response_model=list[PricePoint])
async def get_price_history(
    market_id: str,
    days: int = Query(60, le=365),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.market_id == market_id)
        .where(PriceHistory.recorded_at >= cutoff)
        .order_by(PriceHistory.recorded_at)
    )
    return result.scalars().all()


@router.post("", response_model=MarketDetail, status_code=201)
async def create_market(
    payload: MarketCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check slug unique
    exists = await db.execute(select(Market).where(Market.id == payload.id))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="ID de mercado ya existe")

    # Compute initial LMSR state for desired starting price
    initial_price = max(1.0, min(99.0, payload.initial_yes_price)) / 100.0
    q_yes, q_no = lmsr.init_q_for_price(initial_price, payload.b)

    market = Market(
        id=payload.id,
        question=payload.question,
        description=payload.description,
        category=payload.category,
        resolution_criteria=payload.resolution_criteria,
        ends_at=payload.ends_at,
        b=payload.b,
        q_yes=q_yes,
        q_no=q_no,
        yes_price=lmsr.yes_price_pct(q_yes, q_no, payload.b),
        status=MarketStatus.OPEN,
    )
    db.add(market)

    # Seed first price history point
    ph = PriceHistory(
        market_id=market.id,
        yes_price=market.yes_price,
        volume_snapshot=0.0,
    )
    db.add(ph)

    await db.commit()
    await db.refresh(market)
    return market
