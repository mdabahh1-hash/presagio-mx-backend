"""Tests de Ligas Privadas v1.

Los golden tests del trade path NO se tocan: las ligas solo LEEN precio.
Usa las fixtures de conftest (client, db, make_user, make_binary_market,
make_multi_market, auth_headers).
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select

from app.core.auth import ADMIN_EMAIL
from app.models.league import LeagueCycle, LeagueCycleStanding, LeaguePrediction
from app.models.market import Market, MarketStatus
from app.models.user import User
from app.services.league_engine import (
    compute_payout,
    process_market_resolution_for_leagues,
)
from tests.conftest import auth_headers


# ---------------------------------------------------------------- golden payout

class TestGoldenPayout:
    """Congela el cálculo de payout. Si esto cambia, algo se rompió."""

    def test_payout_basico(self):
        assert compute_payout(Decimal("1000"), Decimal("0.500000")) == Decimal("2000.00")

    def test_payout_favorito(self):
        assert compute_payout(Decimal("1000"), Decimal("0.800000")) == Decimal("1250.00")

    def test_payout_underdog(self):
        assert compute_payout(Decimal("500"), Decimal("0.250000")) == Decimal("2000.00")

    def test_cap_20x(self):
        # precio 0.01 daría 100x, se capea a 20x
        assert compute_payout(Decimal("100"), Decimal("0.010000")) == Decimal("2000.00")

    def test_redondeo_half_up(self):
        # 1000 / 0.3 = 3333.333... -> 3333.33
        assert compute_payout(Decimal("1000"), Decimal("0.300000")) == Decimal("3333.33")


# ---------------------------------------------------------------- helpers / fixtures

async def _setup_league(client, make_user, make_binary_market, n_markets: int):
    """Liga (min 2) con A creador + B miembro, `n_markets` binarios 50/50 y un
    ciclo abierto que los siembra. Regresa dict con ids y headers."""
    a = await make_user("user_a")
    b = await make_user("user_b")
    ha, hb = auth_headers(a), auth_headers(b)

    r = await client.post("/api/leagues", json={"name": "Los compas", "min_members": 2}, headers=ha)
    assert r.status_code == 200, r.text
    league_id, code = r.json()["id"], r.json()["invite_code"]
    r = await client.post(f"/api/leagues/invite/{code}/join", headers=hb)
    assert r.status_code == 200, r.text

    markets = [await make_binary_market(f"lg-m{i}") for i in range(1, n_markets + 1)]

    now = datetime.now(timezone.utc)
    r = await client.post(
        f"/api/leagues/{league_id}/cycles",
        json={
            "name": "Jornada 1",
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(days=60)).isoformat(),
        },
        headers=ha,
    )
    assert r.status_code == 200, r.text
    return {
        "league_id": league_id,
        "code": code,
        "cycle_id": r.json()["id"],
        "market_ids": [m.id for m in markets],
        "a": a, "b": b, "ha": ha, "hb": hb,
    }


@pytest_asyncio.fixture
async def user_a(make_user):
    return auth_headers(await make_user("solo_a"))


@pytest_asyncio.fixture
async def user_b(make_user):
    return auth_headers(await make_user("solo_b"))


@pytest_asyncio.fixture
async def user_c(make_user):
    return auth_headers(await make_user("user_c"))


@pytest_asyncio.fixture
async def league_with_cycle(client, make_user, make_binary_market):
    """(cycle_id, market_id, headers_a) — 1 mercado."""
    s = await _setup_league(client, make_user, make_binary_market, 1)
    return s["cycle_id"], s["market_ids"][0], s["ha"]


async def _pick(client, cycle_id, market_id, side, stake, headers):
    r = await client.post(
        f"/api/cycles/{cycle_id}/predict",
        json={"market_id": market_id, "binary_side": side, "stake": stake},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest_asyncio.fixture
async def seeded_cycle_with_picks(client, make_user, make_binary_market):
    """2 mercados. m1: A yes / B no. m2: A yes / B yes. 1000 PT cada pick."""
    s = await _setup_league(client, make_user, make_binary_market, 2)
    m1, m2 = s["market_ids"]
    await _pick(client, s["cycle_id"], m1, "yes", 1000, s["ha"])
    await _pick(client, s["cycle_id"], m1, "no", 1000, s["hb"])
    await _pick(client, s["cycle_id"], m2, "yes", 1000, s["ha"])
    await _pick(client, s["cycle_id"], m2, "yes", 1000, s["hb"])
    return s


def _fresh(stmt):
    """Relee desde la BD aunque el objeto ya esté en el identity map de la sesión
    (los endpoints escriben en otra sesión). Evita expire_all(), que en async
    dispara lazy-loads (MissingGreenlet) al tocar cualquier atributo."""
    return stmt.execution_options(populate_existing=True)


async def _balances(db, cycle_id) -> dict[int, Decimal]:
    rows = (await db.execute(_fresh(
        select(LeagueCycleStanding).where(LeagueCycleStanding.cycle_id == cycle_id)
    ))).scalars().all()
    return {s.user_id: s.balance for s in rows}


async def _ranks(db, cycle_id) -> dict[int, int | None]:
    rows = (await db.execute(_fresh(
        select(LeagueCycleStanding).where(LeagueCycleStanding.cycle_id == cycle_id)
    ))).scalars().all()
    return {s.user_id: s.final_rank for s in rows}


async def _cycle(db, cycle_id) -> LeagueCycle:
    return (await db.execute(_fresh(select(LeagueCycle).where(LeagueCycle.id == cycle_id)))).scalar_one()


async def _resolve_binary_direct(db, market_id: str, side: str, voided: bool = False):
    """Simula la resolución global (status) + hook, en una transacción."""
    m = (await db.execute(select(Market).where(Market.id == market_id))).scalar_one()
    if voided:
        m.status = MarketStatus.CANCELLED
    else:
        m.status = MarketStatus.RESOLVED_YES if side == "yes" else MarketStatus.RESOLVED_NO
    await process_market_resolution_for_leagues(db, market_id, None, side, voided=voided)
    await db.commit()


# ---------------------------------------------------------------- flujo

class TestLeagueFlow:
    async def test_crear_liga_y_unirse(self, client, user_a, user_b):
        r = await client.post(
            "/api/leagues", json={"name": "Los compas", "min_members": 2}, headers=user_a
        )
        assert r.status_code == 200
        assert r.json()["status"] == "pending"
        code = r.json()["invite_code"]

        # preview público sin auth
        r = await client.get(f"/api/leagues/invite/{code}")
        assert r.status_code == 200
        assert r.json()["member_count"] == 1
        assert r.json()["creator_name"] == "Solo A"

        # se une el segundo y la liga se activa (min_members=2)
        r = await client.post(f"/api/leagues/invite/{code}/join", headers=user_b)
        assert r.status_code == 200
        assert r.json()["status"] == "active"
        assert r.json()["member_count"] == 2

        # unirse dos veces es idempotente
        r = await client.post(f"/api/leagues/invite/{code}/join", headers=user_b)
        assert r.status_code == 200
        assert r.json()["member_count"] == 2

        # /mine lista la liga para ambos
        r = await client.get("/api/leagues/mine", headers=user_b)
        assert [l["invite_code"] for l in r.json()] == [code]

    async def test_ciclo_vacio_422(self, client, user_a):
        r = await client.post("/api/leagues", json={"name": "Vacía", "min_members": 2}, headers=user_a)
        league_id = r.json()["id"]
        now = datetime.now(timezone.utc)
        r = await client.post(
            f"/api/leagues/{league_id}/cycles",
            json={"name": "Nada", "subcategory": "No existe",
                  "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=5)).isoformat()},
            headers=user_a,
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "CYCLE_EMPTY"

    async def test_pick_descuenta_y_es_unico(self, client, league_with_cycle):
        cycle_id, market_id, ha = league_with_cycle
        body = {"market_id": market_id, "binary_side": "yes", "stake": 1000}

        r = await client.post(f"/api/cycles/{cycle_id}/predict", json=body, headers=ha)
        assert r.status_code == 200, r.text
        j = r.json()
        assert Decimal(j["new_balance"]) == Decimal("9000.00")
        assert Decimal(j["price_at_prediction"]) == Decimal("0.500000")  # 50/50 → misma fuente que /quote
        assert Decimal(j["potential_payout"]) == Decimal("2000.00")

        r = await client.post(f"/api/cycles/{cycle_id}/predict", json=body, headers=ha)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "ALREADY_PREDICTED"

    async def test_precio_snapshot_coincide_con_quote(self, client, make_user, make_binary_market):
        """El precio del pick debe ser el mismo spot (mid) que reporta /quote."""
        a = await make_user("quoter")
        ha = auth_headers(a)
        r = await client.post("/api/leagues", json={"name": "Quote", "min_members": 2}, headers=ha)
        league_id = r.json()["id"]
        m = await make_binary_market("lg-skew", b=100.0, initial_yes=0.24)
        now = datetime.now(timezone.utc)
        r = await client.post(
            f"/api/leagues/{league_id}/cycles",
            json={"name": "Jornada", "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=60)).isoformat()},
            headers=ha,
        )
        assert r.status_code == 200, r.text
        cycle_id = r.json()["id"]
        quote = (await client.get(f"/api/markets/{m.id}/quote", params={"side": "NO", "amount": 10})).json()
        j = await _pick(client, cycle_id, m.id, "no", 100, ha)
        # /quote reporta mid_price en % con 2 decimales; el snapshot guarda 6 decimales en (0,1)
        snapshot_pct = (Decimal(j["price_at_prediction"]) * 100).quantize(Decimal("0.01"))
        assert snapshot_pct == Decimal(str(quote["mid_price"]))

    async def test_stake_mayor_al_balance(self, client, league_with_cycle):
        cycle_id, market_id, ha = league_with_cycle
        r = await client.post(
            f"/api/cycles/{cycle_id}/predict",
            json={"market_id": market_id, "binary_side": "no", "stake": 999999},
            headers=ha,
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "INSUFFICIENT_LEAGUE_BALANCE"

    async def test_seleccion_invalida(self, client, league_with_cycle):
        cycle_id, market_id, ha = league_with_cycle
        # binario con outcome_id → 400 INVALID_SELECTION
        r = await client.post(
            f"/api/cycles/{cycle_id}/predict",
            json={"market_id": market_id, "outcome_id": 1, "stake": 100},
            headers=ha,
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_SELECTION"
        # ambos / ninguno → 422 de pydantic
        r = await client.post(
            f"/api/cycles/{cycle_id}/predict",
            json={"market_id": market_id, "stake": 100},
            headers=ha,
        )
        assert r.status_code == 422

    async def test_concurrencia_no_doble_gasto(self, client, make_user, make_binary_market, db):
        """Dos picks simultáneos a mercados distintos con stake 6000 cada uno
        sobre balance 10000: exactamente uno pasa, balance final 4000."""
        s = await _setup_league(client, make_user, make_binary_market, 2)
        m1, m2 = s["market_ids"]

        def post(mid):
            return client.post(
                f"/api/cycles/{s['cycle_id']}/predict",
                json={"market_id": mid, "binary_side": "yes", "stake": 6000},
                headers=s["ha"],
            )

        r1, r2 = await asyncio.gather(post(m1), post(m2))
        codes = sorted([r1.status_code, r2.status_code])
        assert codes == [200, 409], (r1.text, r2.text)
        failed = r1 if r1.status_code == 409 else r2
        assert failed.json()["detail"]["code"] == "INSUFFICIENT_LEAGUE_BALANCE"

        balances = await _balances(db, s["cycle_id"])
        assert balances[s["a"].id] == Decimal("4000.00")
        n_picks = len((await db.execute(
            select(LeaguePrediction).where(LeaguePrediction.user_id == s["a"].id)
        )).scalars().all())
        assert n_picks == 1

    async def test_reveal_bloqueado_antes_del_cierre(self, client, league_with_cycle):
        cycle_id, market_id, ha = league_with_cycle
        r = await client.get(f"/api/cycles/{cycle_id}/reveal/{market_id}", headers=ha)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "MARKET_STILL_OPEN"

    async def test_reveal_tras_cierre(self, client, db, seeded_cycle_with_picks):
        s = seeded_cycle_with_picks
        m1 = s["market_ids"][0]
        await _resolve_binary_direct(db, m1, "yes")
        r = await client.get(f"/api/cycles/{s['cycle_id']}/reveal/{m1}", headers=s["hb"])
        assert r.status_code == 200
        rows = {row["user_id"]: row for row in r.json()}
        assert rows[s["a"].id]["selection_label"] == "Sí" and rows[s["a"].id]["status"] == "won"
        assert rows[s["b"].id]["selection_label"] == "No" and rows[s["b"].id]["status"] == "lost"

    async def test_no_miembro_403(self, client, league_with_cycle, user_c):
        cycle_id, market_id, _ = league_with_cycle
        r = await client.post(
            f"/api/cycles/{cycle_id}/predict",
            json={"market_id": market_id, "binary_side": "yes", "stake": 500},
            headers=user_c,
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "NOT_MEMBER"
        r = await client.get(f"/api/leagues/{1}", headers=user_c)
        assert r.status_code == 403

    async def test_detalle_incluye_precios_y_mi_pick(self, client, seeded_cycle_with_picks):
        s = seeded_cycle_with_picks
        r = await client.get(f"/api/leagues/{s['league_id']}", headers=s["ha"])
        assert r.status_code == 200, r.text
        d = r.json()
        cyc = d["current_cycle"]
        assert cyc["my_balance"] == "8000.00"
        assert len(cyc["markets"]) == 2
        m = cyc["markets"][0]
        assert m["is_open"] is True
        assert m["predicted_count"] == 2
        assert {o["side"] for o in m["outcomes"]} == {"yes", "no"}
        assert m["my_prediction"]["binary_side"] == "yes"
        # los picks ajenos NO se exponen aquí
        assert "predictions" not in m


# ---------------------------------------------------------------- resolución

class TestResolution:
    async def test_won_lost_void(self, db, seeded_cycle_with_picks):
        """won = stake/price (0.5 → 2x), lost = 0, void devuelve el stake."""
        s = seeded_cycle_with_picks
        m1, m2 = s["market_ids"]
        a, b = s["a"].id, s["b"].id

        # Ambos gastaron 2×1000 → 8000
        assert (await _balances(db, s["cycle_id"])) == {a: Decimal("8000.00"), b: Decimal("8000.00")}

        await _resolve_binary_direct(db, m1, "yes")
        bal = await _balances(db, s["cycle_id"])
        assert bal[a] == Decimal("10000.00")  # +2000.00
        assert bal[b] == Decimal("8000.00")   # lost → 0

        preds = {(p.user_id): p for p in (await db.execute(_fresh(
            select(LeaguePrediction).where(LeaguePrediction.market_id == m1)
        ))).scalars().all()}
        assert preds[a].status == "won" and preds[a].payout == Decimal("2000.00")
        assert preds[b].status == "lost" and preds[b].payout == Decimal("0.00")

        await _resolve_binary_direct(db, m2, "no", voided=True)
        bal = await _balances(db, s["cycle_id"])
        assert bal[a] == Decimal("11000.00")
        assert bal[b] == Decimal("9000.00")
        p_void = (await db.execute(_fresh(
            select(LeaguePrediction).where(LeaguePrediction.market_id == m2, LeaguePrediction.user_id == a)
        ))).scalar_one()
        assert p_void.status == "void" and p_void.payout == Decimal("1000.00")

        # Hook idempotente: volver a llamar no paga dos veces
        await process_market_resolution_for_leagues(db, m1, None, "yes")
        await db.commit()
        assert (await _balances(db, s["cycle_id"]))[a] == Decimal("11000.00")

    async def test_ciclo_resuelve_solo_al_final(self, db, seeded_cycle_with_picks):
        """Con 2 mercados, resolver 1 deja el ciclo open; resolver el segundo lo
        pasa a resolved con final_rank correcto."""
        s = seeded_cycle_with_picks
        m1, m2 = s["market_ids"]
        a, b = s["a"].id, s["b"].id

        await _resolve_binary_direct(db, m1, "yes")
        cycle = await _cycle(db, s["cycle_id"])
        assert cycle.status == "open"
        assert (await _ranks(db, s["cycle_id"])) == {a: None, b: None}

        await _resolve_binary_direct(db, m2, "yes")
        cycle = await _cycle(db, s["cycle_id"])
        assert cycle.status == "resolved" and cycle.resolved_at is not None
        # A: 8000+2000+2000 = 12000 ; B: 8000+0+2000 = 10000
        assert (await _balances(db, s["cycle_id"])) == {a: Decimal("12000.00"), b: Decimal("10000.00")}
        assert (await _ranks(db, s["cycle_id"])) == {a: 1, b: 2}

    async def test_empate_comparte_rank(self, client, db, make_user, make_binary_market):
        s = await _setup_league(client, make_user, make_binary_market, 1)
        m1 = s["market_ids"][0]
        await _pick(client, s["cycle_id"], m1, "yes", 1000, s["ha"])
        await _pick(client, s["cycle_id"], m1, "yes", 1000, s["hb"])
        await _resolve_binary_direct(db, m1, "yes")
        assert (await _ranks(db, s["cycle_id"])) == {s["a"].id: 1, s["b"].id: 1}

    async def test_hook_via_endpoint_admin(self, client, db, seeded_cycle_with_picks):
        """El flujo admin real de resolución dispara el hook (binario)."""
        s = seeded_cycle_with_picks
        m1 = s["market_ids"][0]
        admin = User(email=ADMIN_EMAIL, username="admin", display_name="Admin", email_verified=True, points=0)
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

        r = await client.post(
            f"/api/admin/markets/{m1}/resolve", json={"resolution": "NO"}, headers=auth_headers(admin)
        )
        assert r.status_code == 200, r.text
        bal = await _balances(db, s["cycle_id"])
        assert bal[s["a"].id] == Decimal("8000.00")   # A dijo yes → lost
        assert bal[s["b"].id] == Decimal("10000.00")  # B dijo no → won

    async def test_hook_multi_via_endpoint_admin(self, client, db, make_user, make_multi_market):
        """Mercado multi: el pick usa outcome_id y el admin resuelve por outcome_key."""
        a = await make_user("multi_a")
        ha = auth_headers(a)
        r = await client.post("/api/leagues", json={"name": "Multi", "min_members": 2}, headers=ha)
        league_id = r.json()["id"]
        m = await make_multi_market("lg-multi", outcome_keys=("A", "B", "C"))
        now = datetime.now(timezone.utc)
        r = await client.post(
            f"/api/leagues/{league_id}/cycles",
            json={"name": "Jornada", "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=60)).isoformat()},
            headers=ha,
        )
        assert r.status_code == 200, r.text
        cycle_id = r.json()["id"]

        detail = (await client.get(f"/api/leagues/{league_id}", headers=ha)).json()
        outcomes = detail["current_cycle"]["markets"][0]["outcomes"]
        by_key = {o["outcome_key"]: o for o in outcomes}
        assert Decimal(by_key["B"]["price"]) == Decimal("0.333333")

        r = await client.post(
            f"/api/cycles/{cycle_id}/predict",
            json={"market_id": m.id, "outcome_id": by_key["B"]["id"], "stake": 300},
            headers=ha,
        )
        assert r.status_code == 200, r.text
        assert Decimal(r.json()["potential_payout"]) == Decimal("900.00")  # 300/0.333333 = 900.0009 → 900.00

        admin = User(email=ADMIN_EMAIL, username="admin", display_name="Admin", email_verified=True, points=0)
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        r = await client.post(
            f"/api/admin/markets/{m.id}/resolve", json={"outcome_key": "B"}, headers=auth_headers(admin)
        )
        assert r.status_code == 200, r.text
        bal = await _balances(db, cycle_id)
        assert bal[a.id] == Decimal("10600.00")  # 10000 - 300 + 900
        cycle = await _cycle(db, cycle_id)
        assert cycle.status == "resolved"
