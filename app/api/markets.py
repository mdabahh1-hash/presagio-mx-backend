from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, case, func
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.market import Market, MarketStatus, MarketCategory
from app.models.price_history import PriceHistory
from app.schemas.market import MarketList, MarketDetail, MarketCreate, MarketKind, PricePoint, MoverOut, ResumenCategoria, CategoriaActivos, EnVivoOut
from app.core.auth import get_current_user, require_admin
from app.core import lmsr
from app.models.user import User
from app.services.movers import calcular_movers
from app.services.resumen import resumen_categoria
from app.services import en_vivo
from app.config import settings

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=list[MarketList])
async def list_markets(
    category: MarketCategory | None = Query(None),
    subcategory: str | None = Query(None, max_length=50),
    kind: MarketKind | None = Query(None),  # 'partido' | 'accesorio' (Deportes)
    status: str = Query("active"),  # "active" = open + pending_resolution
    trending: bool | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("volume"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Market)
    # "active" keeps expired-but-unresolved markets visible (they can't be
    # traded — the trade/quote guards reject non-OPEN); resolved ones drop out.
    _ACTIVE = (MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION)
    if status == "active":
        stmt = stmt.where(Market.status.in_(_ACTIVE))
    elif status != "all":
        try:
            status_enum = MarketStatus(status)
            stmt = stmt.where(Market.status == status_enum)
        except ValueError:
            stmt = stmt.where(Market.status.in_(_ACTIVE))  # fallback = default
    if category:
        stmt = stmt.where(Market.category == category)
    if subcategory:
        stmt = stmt.where(Market.subcategory == subcategory)
    if kind:
        stmt = stmt.where(Market.kind == kind)
    if trending is not None:
        stmt = stmt.where(Market.trending == trending)
    if q:
        stmt = stmt.where(Market.question.ilike(f"%{q}%"))

    if sort == "volume":
        stmt = stmt.order_by(desc(Market.volume), Market.id)
    elif sort == "liquidity":
        stmt = stmt.order_by(desc(Market.b), Market.id)
    elif sort == "trending":
        stmt = stmt.order_by(desc(Market.trending), desc(Market.volume), Market.id)
    elif sort == "ending":
        # "Closing soon" = open markets by closest close; already-expired
        # (pending_resolution) ones go last instead of topping the list.
        pending_last = case((Market.status == MarketStatus.PENDING_RESOLUTION, 1), else_=0)
        stmt = stmt.order_by(pending_last, Market.ends_at, Market.id)
    elif sort == "new":
        # Pestaña "Nuevo": lo último sembrado primero; los ya vencidos al final.
        pending_last = case((Market.status == MarketStatus.PENDING_RESOLUTION, 1), else_=0)
        stmt = stmt.order_by(pending_last, desc(Market.created_at), Market.id)
    else:
        stmt = stmt.order_by(desc(Market.volume), Market.id)

    stmt = stmt.limit(limit).offset(offset).options(selectinload(Market.outcomes))
    result = await db.execute(stmt)
    return result.scalars().all()


# Va antes de /{market_id} para que la ruta dinámica no lo capture.
@router.get("/movers", response_model=list[MoverOut])
async def list_movers(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(50, ge=1, le=100),
    category: MarketCategory | None = Query(None),
    subcategory: str | None = Query(None, max_length=50),
    db: AsyncSession = Depends(get_db),
):
    """Página "Noticias": mercados que más se movieron en las últimas `hours`
    horas, por |cambio| en puntos porcentuales (ver app/services/movers.py).
    `category`/`subcategory` acotan (landing de Deportes: movimiento de una liga)."""
    return await calcular_movers(db, hours, limit, category, subcategory)


@router.get("/resumen", response_model=ResumenCategoria)
async def get_resumen(
    category: MarketCategory = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Agregados de una categoría para su landing: mercados abiertos y volumen
    (total y de 7 días) por subcategoría (ver app/services/resumen.py)."""
    return await resumen_categoria(db, category)


@router.get("/categorias", response_model=list[CategoriaActivos])
async def list_categorias(db: AsyncSession = Depends(get_db)):
    """Categorías con mercados activos (OPEN + PENDING_RESOLUTION, como el default de
    GET /markets) y cuántos. Las categorías sin ninguno no aparecen: la barra del
    frontend las oculta (salvo las de landing propia)."""
    res = await db.execute(
        select(Market.category, func.count(Market.id))
        .where(Market.status.in_([MarketStatus.OPEN, MarketStatus.PENDING_RESOLUTION]))
        .group_by(Market.category)
    )
    return [{"categoria": cat, "activos": n} for cat, n in res.all()]


@router.get("/en-vivo", response_model=list[EnVivoOut])
async def list_en_vivo():
    """Marcador y minuto de los partidos en ventana (poller de ESPN, app/services/en_vivo.py).
    [] si el poller está apagado (EN_VIVO_ENABLED)."""
    if not settings.EN_VIVO_ENABLED:
        return []
    return en_vivo.estados()


@router.get("/{market_id}", response_model=MarketDetail)
async def get_market(market_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Market).where(Market.id == market_id).options(selectinload(Market.outcomes))
    )
    market = result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail={"code": "MARKET_NOT_FOUND", "message": "Mercado no encontrado"})
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
    require_admin(current_user)
    # Accesorios de jugador (touchdown / pases / fantasy / titular / gol) solo por
    # YAML: necesitan `sujeto` con ids por fuente (sembrar-mercados.py identificar).
    # Los accesorios de equipo o de evento no parsean como prop y siguen pasando.
    from app.services.resolucion.sujeto import requiere_sujeto

    if requiere_sujeto(payload.category, "binary", payload.subcategory, payload.question):
        raise HTTPException(status_code=422, detail={
            "code": "ACCESORIO_SOLO_YAML",
            "message": "Los accesorios de jugador se siembran por mercados-pendientes.yaml con sujeto (sembrar-mercados.py identificar)",
        })
    # Check slug unique
    exists = await db.execute(select(Market).where(Market.id == payload.id))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail={"code": "MARKET_ID_EXISTS", "message": "ID de mercado ya existe"})

    # Compute initial LMSR state for desired starting price
    initial_price = max(1.0, min(99.0, payload.initial_yes_price)) / 100.0
    q_yes, q_no = lmsr.init_q_for_price(initial_price, payload.b)

    market = Market(
        id=payload.id,
        question=payload.question,
        description=payload.description,
        category=payload.category,
        subcategory=payload.subcategory,
        resolution_criteria=payload.resolution_criteria,
        resolution_source_url=payload.resolution_source_url,
        rules=payload.rules,
        context=payload.context,
        image_url=payload.image_url,
        kind=payload.kind,
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
    # Re-fetch with outcomes eager-loaded; the MarketDetail response serializes
    # the (lazy) outcomes relationship, which would otherwise error in async.
    result = await db.execute(
        select(Market).where(Market.id == market.id).options(selectinload(Market.outcomes))
    )
    return result.scalar_one()
