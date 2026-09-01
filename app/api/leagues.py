"""
Router de Ligas Privadas v1.

REGLA DURA: nada de aquí toca el trade path ni el AMM. Los picks solo LEEN
el precio marginal actual vía app.services.league_engine (misma fuente que
GET /markets/{id}/quote).
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_admin
from app.database import get_db
from app.models.league import (
    League,
    LeagueCycle,
    LeagueCycleMarket,
    LeagueCycleStanding,
    LeagueMember,
    LeaguePrediction,
)
from app.models.market import Market, MarketStatus
from app.models.outcome import Outcome
from app.models.user import User
from app.schemas.league import (
    CycleCreate,
    CycleMarketOut,
    CycleOut,
    InvitePreview,
    LeagueCreate,
    LeagueDetail,
    LeagueSummary,
    MemberOut,
    PredictionCreate,
    PredictionOut,
    RevealRow,
    StandingOut,
)
from app.services.league_engine import (
    RESOLVED_STATUSES,
    compute_payout,
    create_standings_for_members,
    generate_invite_code,
    get_snapshot_price,
    maybe_resolve_cycle,
    now_utc,
    q2,
    seed_cycle_markets,
    snapshot_prices,
)

router = APIRouter(tags=["leagues"])


def api_error(status: int, code: str, message: str) -> HTTPException:
    """Mismo shape {code, message} que el resto de la API (translateApiError en el frontend)."""
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def market_is_open(market: Market) -> bool:
    return market.status == MarketStatus.OPEN and market.ends_at > now_utc()


def market_is_closed_or_resolved(market: Market) -> bool:
    return market.ends_at <= now_utc() or market.status in RESOLVED_STATUSES


# ================================================================ ligas

@router.post("/leagues", response_model=LeagueSummary)
async def create_league(
    body: LeagueCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    for _ in range(5):
        code = generate_invite_code()
        league = League(
            name=body.name.strip(),
            creator_id=user.id,
            invite_code=code,
            min_members=body.min_members,
        )
        db.add(league)
        try:
            await db.flush()
            break
        except IntegrityError:
            await db.rollback()
    else:
        raise api_error(500, "INVITE_CODE_COLLISION", "No se pudo generar el código")

    db.add(LeagueMember(league_id=league.id, user_id=user.id, role="creator"))
    await db.commit()

    return LeagueSummary(
        id=league.id,
        name=league.name,
        status=league.status,
        invite_code=league.invite_code,
        member_count=1,
        min_members=league.min_members,
    )


@router.get("/leagues/mine", response_model=list[LeagueSummary])
async def my_leagues(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memberships = (
        (
            await db.execute(
                select(League)
                .join(LeagueMember, LeagueMember.league_id == League.id)
                .where(LeagueMember.user_id == user.id)
                .order_by(League.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    out: list[LeagueSummary] = []
    for league in memberships:
        member_count = (
            await db.execute(
                select(func.count()).select_from(LeagueMember).where(
                    LeagueMember.league_id == league.id
                )
            )
        ).scalar_one()

        cycle = (
            await db.execute(
                select(LeagueCycle)
                .where(LeagueCycle.league_id == league.id)
                .order_by(LeagueCycle.cycle_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        my_rank = None
        pending = 0
        if cycle:
            standing = (
                await db.execute(
                    select(LeagueCycleStanding).where(
                        LeagueCycleStanding.cycle_id == cycle.id,
                        LeagueCycleStanding.user_id == user.id,
                    )
                )
            ).scalar_one_or_none()
            if standing and standing.final_rank:
                my_rank = standing.final_rank
            if cycle.status == "open":
                total_markets = (
                    await db.execute(
                        select(func.count())
                        .select_from(LeagueCycleMarket)
                        .where(LeagueCycleMarket.cycle_id == cycle.id)
                    )
                ).scalar_one()
                my_picks = (
                    await db.execute(
                        select(func.count())
                        .select_from(LeaguePrediction)
                        .where(
                            LeaguePrediction.cycle_id == cycle.id,
                            LeaguePrediction.user_id == user.id,
                        )
                    )
                ).scalar_one()
                pending = max(total_markets - my_picks, 0)

        out.append(
            LeagueSummary(
                id=league.id,
                name=league.name,
                status=league.status,
                invite_code=league.invite_code,
                member_count=member_count,
                min_members=league.min_members,
                cycle_name=cycle.name if cycle else None,
                my_rank=my_rank,
                pending_picks=pending,
            )
        )
    return out


@router.get("/leagues/invite/{code}", response_model=InvitePreview)
async def invite_preview(code: str, db: AsyncSession = Depends(get_db)):
    """PÚBLICO. Preview para la landing de invitación, sin auth."""
    league = (
        await db.execute(select(League).where(League.invite_code == code.lower()))
    ).scalar_one_or_none()
    if not league:
        raise api_error(404, "LEAGUE_NOT_FOUND", "Esta liga no existe")

    member_count = (
        await db.execute(
            select(func.count()).select_from(LeagueMember).where(
                LeagueMember.league_id == league.id
            )
        )
    ).scalar_one()

    creator = (
        await db.execute(select(User).where(User.id == league.creator_id))
    ).scalar_one()

    cycle = (
        await db.execute(
            select(LeagueCycle)
            .where(LeagueCycle.league_id == league.id, LeagueCycle.status == "open")
            .limit(1)
        )
    ).scalar_one_or_none()

    return InvitePreview(
        name=league.name,
        creator_name=creator.display_name,
        member_count=member_count,
        min_members=league.min_members,
        status=league.status,
        cycle_name=cycle.name if cycle else None,
        cycle_ends_at=cycle.ends_at if cycle else None,
    )


@router.post("/leagues/invite/{code}/join", response_model=LeagueSummary)
async def join_league(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    league = (
        await db.execute(
            select(League).where(League.invite_code == code.lower()).with_for_update()
        )
    ).scalar_one_or_none()
    if not league:
        raise api_error(404, "LEAGUE_NOT_FOUND", "Esta liga no existe")
    if league.status == "archived":
        raise api_error(409, "LEAGUE_ARCHIVED", "Esta liga ya terminó")

    existing = (
        await db.execute(
            select(LeagueMember).where(
                LeagueMember.league_id == league.id, LeagueMember.user_id == user.id
            )
        )
    ).scalar_one_or_none()

    if not existing:
        db.add(LeagueMember(league_id=league.id, user_id=user.id, role="member"))

        # si hay ciclo abierto, entra parejo con el stack inicial
        cycle = (
            await db.execute(
                select(LeagueCycle).where(
                    LeagueCycle.league_id == league.id, LeagueCycle.status == "open"
                )
            )
        ).scalar_one_or_none()
        if cycle:
            db.add(
                LeagueCycleStanding(
                    cycle_id=cycle.id, user_id=user.id, balance=cycle.initial_stack
                )
            )

    # flush explícito: el count de abajo ya incluye al miembro recién agregado
    await db.flush()
    member_count = (
        await db.execute(
            select(func.count()).select_from(LeagueMember).where(
                LeagueMember.league_id == league.id
            )
        )
    ).scalar_one()

    if league.status == "pending" and member_count >= league.min_members:
        league.status = "active"

    await db.commit()

    return LeagueSummary(
        id=league.id,
        name=league.name,
        status=league.status,
        invite_code=league.invite_code,
        member_count=member_count,
        min_members=league.min_members,
    )


# ================================================================ detalle

async def serialize_outcomes(db: AsyncSession, market: Market) -> list[dict]:
    """
    Precios actuales por outcome para pintar el PickSheet (misma fuente que
    /quote). Binario: [{"side","price"}]; multi: [{"id","outcome_key","label","price"}].
    """
    prices = await snapshot_prices(db, market)
    if market.market_type == "multi":
        rows = sorted(prices.values(), key=lambda t: t[1], reverse=True)
        return [
            {"id": o.id, "outcome_key": o.outcome_key, "label": o.label, "price": str(p)}
            for o, p in rows
        ]
    return [
        {"side": "yes", "price": str(prices["yes"])},
        {"side": "no", "price": str(prices["no"])},
    ]


@router.get("/leagues/{league_id}", response_model=LeagueDetail)
async def league_detail(
    league_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    league = (
        await db.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()
    if not league:
        raise api_error(404, "LEAGUE_NOT_FOUND", "Esta liga no existe")

    membership = (
        await db.execute(
            select(LeagueMember).where(
                LeagueMember.league_id == league_id, LeagueMember.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if not membership:
        raise api_error(403, "NOT_MEMBER", "No eres miembro de esta liga")

    member_rows = (
        await db.execute(
            select(LeagueMember, User)
            .join(User, User.id == LeagueMember.user_id)
            .where(LeagueMember.league_id == league_id)
        )
    ).all()
    members = [
        MemberOut(user_id=m.user_id, display_name=u.display_name, role=m.role)
        for m, u in member_rows
    ]
    names = {m.user_id: u.display_name for m, u in member_rows}

    cycle = (
        await db.execute(
            select(LeagueCycle)
            .where(LeagueCycle.league_id == league_id)
            .order_by(LeagueCycle.cycle_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    cycle_out = None
    standings_out: list[StandingOut] = []

    if cycle:
        rows = (
            await db.execute(
                select(Market)
                .join(LeagueCycleMarket, LeagueCycleMarket.market_id == Market.id)
                .where(LeagueCycleMarket.cycle_id == cycle.id)
                .order_by(Market.ends_at.asc())
            )
        ).scalars().all()

        my_preds = {
            p.market_id: p
            for p in (
                await db.execute(
                    select(LeaguePrediction).where(
                        LeaguePrediction.cycle_id == cycle.id,
                        LeaguePrediction.user_id == user.id,
                    )
                )
            )
            .scalars()
            .all()
        }

        counts = dict(
            (
                await db.execute(
                    select(LeaguePrediction.market_id, func.count())
                    .where(LeaguePrediction.cycle_id == cycle.id)
                    .group_by(LeaguePrediction.market_id)
                )
            ).all()
        )

        markets_out = []
        for m in rows:
            mp = my_preds.get(m.id)
            markets_out.append(
                CycleMarketOut(
                    market_id=m.id,
                    question=m.question,
                    market_type=m.market_type,
                    closes_at=m.ends_at,
                    is_open=market_is_open(m),
                    outcomes=await serialize_outcomes(db, m),
                    predicted_count=counts.get(m.id, 0),
                    my_prediction=(
                        {
                            "outcome_id": mp.outcome_id,
                            "binary_side": mp.binary_side,
                            "stake": str(mp.stake),
                            "price_at_prediction": str(mp.price_at_prediction),
                            "status": mp.status,
                            "payout": str(mp.payout) if mp.payout is not None else None,
                        }
                        if mp
                        else None
                    ),
                )
            )

        standing_rows = (
            await db.execute(
                select(LeagueCycleStanding)
                .where(LeagueCycleStanding.cycle_id == cycle.id)
                .order_by(LeagueCycleStanding.balance.desc())
            )
        ).scalars().all()

        hits = dict(
            (
                await db.execute(
                    select(
                        LeaguePrediction.user_id,
                        func.count().filter(LeaguePrediction.status == "won"),
                    )
                    .where(LeaguePrediction.cycle_id == cycle.id)
                    .group_by(LeaguePrediction.user_id)
                )
            ).all()
        )
        resolved_counts = dict(
            (
                await db.execute(
                    select(
                        LeaguePrediction.user_id,
                        func.count().filter(
                            LeaguePrediction.status.in_(("won", "lost"))
                        ),
                    )
                    .where(LeaguePrediction.cycle_id == cycle.id)
                    .group_by(LeaguePrediction.user_id)
                )
            ).all()
        )

        my_balance = None
        for s in standing_rows:
            if s.user_id == user.id:
                my_balance = str(s.balance)
            standings_out.append(
                StandingOut(
                    user_id=s.user_id,
                    display_name=names.get(s.user_id, "—"),
                    balance=str(s.balance),
                    hits=hits.get(s.user_id, 0) or 0,
                    total_resolved=resolved_counts.get(s.user_id, 0) or 0,
                    final_rank=s.final_rank,
                    is_me=s.user_id == user.id,
                )
            )

        cycle_out = CycleOut(
            id=cycle.id,
            cycle_number=cycle.cycle_number,
            name=cycle.name,
            status=cycle.status,
            initial_stack=str(cycle.initial_stack),
            starts_at=cycle.starts_at,
            ends_at=cycle.ends_at,
            my_balance=my_balance,
            markets=markets_out,
        )

    return LeagueDetail(
        id=league.id,
        name=league.name,
        status=league.status,
        invite_code=league.invite_code,
        creator_id=league.creator_id,
        min_members=league.min_members,
        members=members,
        current_cycle=cycle_out,
        standings=standings_out,
    )


# ================================================================ ciclos

@router.post("/leagues/{league_id}/cycles", response_model=CycleOut)
async def create_cycle(
    league_id: int,
    body: CycleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    league = (
        await db.execute(select(League).where(League.id == league_id))
    ).scalar_one_or_none()
    if not league:
        raise api_error(404, "LEAGUE_NOT_FOUND", "Esta liga no existe")
    if league.creator_id != user.id:
        raise api_error(403, "NOT_CREATOR", "Solo quien creó la liga puede abrir ciclos")

    open_cycle = (
        await db.execute(
            select(LeagueCycle).where(
                LeagueCycle.league_id == league_id, LeagueCycle.status.in_(("open", "scoring"))
            )
        )
    ).scalar_one_or_none()
    if open_cycle:
        raise api_error(409, "CYCLE_ALREADY_OPEN", "Ya hay un ciclo en curso")

    last_number = (
        await db.execute(
            select(func.coalesce(func.max(LeagueCycle.cycle_number), 0)).where(
                LeagueCycle.league_id == league_id
            )
        )
    ).scalar_one()

    cycle = LeagueCycle(
        league_id=league_id,
        cycle_number=last_number + 1,
        name=body.name.strip(),
        subcategory=body.subcategory,
        initial_stack=body.initial_stack,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
    )
    db.add(cycle)
    await db.flush()

    seeded = await seed_cycle_markets(db, cycle)
    if seeded == 0:
        await db.rollback()
        raise api_error(
            422,
            "CYCLE_EMPTY",
            "No hay mercados abiertos en esa subcategoría y fechas",
        )

    member_ids = (
        (
            await db.execute(
                select(LeagueMember.user_id).where(LeagueMember.league_id == league_id)
            )
        )
        .scalars()
        .all()
    )
    await create_standings_for_members(db, cycle, member_ids)
    await db.commit()

    return CycleOut(
        id=cycle.id,
        cycle_number=cycle.cycle_number,
        name=cycle.name,
        status=cycle.status,
        initial_stack=str(cycle.initial_stack),
        starts_at=cycle.starts_at,
        ends_at=cycle.ends_at,
    )


# ================================================================ picks

@router.post("/cycles/{cycle_id}/predict", response_model=PredictionOut)
async def predict(
    cycle_id: int,
    body: PredictionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cycle = (
        await db.execute(select(LeagueCycle).where(LeagueCycle.id == cycle_id))
    ).scalar_one_or_none()
    if not cycle:
        raise api_error(404, "CYCLE_NOT_FOUND", "Este ciclo no existe")

    membership = (
        await db.execute(
            select(LeagueMember).where(
                LeagueMember.league_id == cycle.league_id,
                LeagueMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not membership:
        raise api_error(403, "NOT_MEMBER", "No eres miembro de esta liga")

    if cycle.status != "open":
        raise api_error(409, "CYCLE_CLOSED", "Este ciclo ya cerró")

    in_cycle = (
        await db.execute(
            select(LeagueCycleMarket).where(
                LeagueCycleMarket.cycle_id == cycle_id,
                LeagueCycleMarket.market_id == body.market_id,
            )
        )
    ).scalar_one_or_none()
    if not in_cycle:
        raise api_error(404, "MARKET_NOT_IN_CYCLE", "Ese mercado no es de este ciclo")

    market = (
        await db.execute(select(Market).where(Market.id == body.market_id))
    ).scalar_one()
    if not market_is_open(market):
        raise api_error(409, "MARKET_CLOSED", "Ese mercado ya cerró")

    # lock del standing para evitar doble gasto concurrente
    standing = (
        await db.execute(
            select(LeagueCycleStanding)
            .where(
                LeagueCycleStanding.cycle_id == cycle_id,
                LeagueCycleStanding.user_id == user.id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not standing:
        raise api_error(409, "NO_STANDING", "No estás inscrito en este ciclo")

    if body.stake > standing.balance:
        raise api_error(
            409, "INSUFFICIENT_LEAGUE_BALANCE", "No te alcanzan los puntos de liga"
        )

    try:
        price = await get_snapshot_price(db, market, body.outcome_id, body.binary_side)
    except ValueError as e:
        raise api_error(400, "INVALID_SELECTION", str(e))
    if not (Decimal("0") < price < Decimal("1")):
        raise api_error(409, "INVALID_PRICE", "Precio inválido, intenta de nuevo")

    prediction = LeaguePrediction(
        cycle_id=cycle_id,
        user_id=user.id,
        market_id=body.market_id,
        outcome_id=body.outcome_id,
        binary_side=body.binary_side,
        stake=q2(body.stake),
        price_at_prediction=price,
    )
    db.add(prediction)
    standing.balance = q2(standing.balance - body.stake)
    new_balance = standing.balance

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise api_error(409, "ALREADY_PREDICTED", "Ya hiciste tu pick en ese mercado")

    return PredictionOut(
        id=prediction.id,
        market_id=prediction.market_id,
        outcome_id=prediction.outcome_id,
        binary_side=prediction.binary_side,
        stake=str(prediction.stake),
        price_at_prediction=str(prediction.price_at_prediction),
        potential_payout=str(compute_payout(prediction.stake, price)),
        status=prediction.status,
        new_balance=str(new_balance),
    )


# ================================================================ standings y reveal

async def _require_member(db: AsyncSession, cycle_id: int, user: User) -> LeagueCycle:
    cycle = (
        await db.execute(select(LeagueCycle).where(LeagueCycle.id == cycle_id))
    ).scalar_one_or_none()
    if not cycle:
        raise api_error(404, "CYCLE_NOT_FOUND", "Este ciclo no existe")

    membership = (
        await db.execute(
            select(LeagueMember).where(
                LeagueMember.league_id == cycle.league_id,
                LeagueMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not membership:
        raise api_error(403, "NOT_MEMBER", "No eres miembro de esta liga")
    return cycle


@router.get("/cycles/{cycle_id}/standings", response_model=list[StandingOut])
async def cycle_standings(
    cycle_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_member(db, cycle_id, user)

    rows = (
        await db.execute(
            select(LeagueCycleStanding, User)
            .join(User, User.id == LeagueCycleStanding.user_id)
            .where(LeagueCycleStanding.cycle_id == cycle_id)
            .order_by(LeagueCycleStanding.balance.desc())
        )
    ).all()

    hits = dict(
        (
            await db.execute(
                select(
                    LeaguePrediction.user_id,
                    func.count().filter(LeaguePrediction.status == "won"),
                )
                .where(LeaguePrediction.cycle_id == cycle_id)
                .group_by(LeaguePrediction.user_id)
            )
        ).all()
    )
    resolved = dict(
        (
            await db.execute(
                select(
                    LeaguePrediction.user_id,
                    func.count().filter(LeaguePrediction.status.in_(("won", "lost"))),
                )
                .where(LeaguePrediction.cycle_id == cycle_id)
                .group_by(LeaguePrediction.user_id)
            )
        ).all()
    )

    return [
        StandingOut(
            user_id=s.user_id,
            display_name=u.display_name,
            balance=str(s.balance),
            hits=hits.get(s.user_id, 0) or 0,
            total_resolved=resolved.get(s.user_id, 0) or 0,
            final_rank=s.final_rank,
            is_me=s.user_id == user.id,
        )
        for s, u in rows
    ]


@router.get("/cycles/{cycle_id}/reveal/{market_id}", response_model=list[RevealRow])
async def reveal_market_picks(
    cycle_id: int,
    market_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    REGLA DE PRIVACIDAD DURA: solo revela picks si el mercado YA CERRÓ.
    Antes del cierre, 409. Ningún otro endpoint expone picks ajenos.
    """
    await _require_member(db, cycle_id, user)

    market = (
        await db.execute(select(Market).where(Market.id == market_id))
    ).scalar_one_or_none()
    if not market:
        raise api_error(404, "MARKET_NOT_FOUND", "Ese mercado no existe")
    if not market_is_closed_or_resolved(market):
        raise api_error(409, "MARKET_STILL_OPEN", "Los picks se revelan al cierre")

    rows = (
        await db.execute(
            select(LeaguePrediction, User)
            .join(User, User.id == LeaguePrediction.user_id)
            .where(
                LeaguePrediction.cycle_id == cycle_id,
                LeaguePrediction.market_id == market_id,
            )
            .order_by(LeaguePrediction.stake.desc())
        )
    ).all()

    labels: dict[int, str] = {}
    if market.market_type == "multi":
        outcomes = (
            await db.execute(select(Outcome).where(Outcome.market_id == market_id))
        ).scalars().all()
        labels = {o.id: o.label for o in outcomes}

    out: list[RevealRow] = []
    for p, u in rows:
        if p.outcome_id is not None:
            label = labels.get(p.outcome_id, "—")
        else:
            label = "Sí" if p.binary_side == "yes" else "No"
        out.append(
            RevealRow(
                user_id=p.user_id,
                display_name=u.display_name,
                selection_label=label,
                stake=str(p.stake),
                status=p.status,
                payout=str(p.payout) if p.payout is not None else None,
            )
        )
    return out


# ================================================================ admin

@router.post("/admin/cycles/{cycle_id}/resolve")
async def admin_resolve_cycle(
    cycle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Palanca manual por si el hook automático falla."""
    require_admin(current_user)
    resolved = await maybe_resolve_cycle(db, cycle_id)
    await db.commit()
    return {"resolved": resolved}
