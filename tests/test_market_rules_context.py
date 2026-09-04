"""markets.rules / markets.context: opcionales, solo en el detalle, se aceptan al crear."""
import pytest
from datetime import datetime, timedelta, timezone

from app.core.auth import ADMIN_EMAIL
from app.models.market import Market, MarketCategory, MarketStatus
from app.models.user import User
from tests.conftest import auth_headers

RULES = "Cómo se resuelve: consenso de dos medios.\n\nSi el evento se pospone, el mercado se mantiene."
CONTEXT = "Antecedentes del mercado."


@pytest.mark.asyncio
async def test_rules_context_default_to_null(client, make_binary_market):
    m = await make_binary_market("rc-none")
    assert m.rules is None and m.context is None
    resp = await client.get(f"/api/markets/{m.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rules"] is None
    assert body["context"] is None


@pytest.mark.asyncio
async def test_rules_context_roundtrip_detail_only(client, db):
    m = Market(
        id="rc-set",
        question="¿Test normas?",
        description="Mercado con normas y contexto",
        category=MarketCategory.DEPORTES,
        subcategory="Liga MX",
        resolution_criteria="Prueba",
        resolution_source_url="https://ligamx.net/cancha/resultados",
        rules=RULES,
        context=CONTEXT,
        ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        b=1000.0, q_yes=0.0, q_no=0.0, yes_price=50.0,
        status=MarketStatus.OPEN, market_type="binary",
    )
    db.add(m)
    await db.commit()

    detail = (await client.get("/api/markets/rc-set")).json()
    assert detail["rules"] == RULES
    assert detail["context"] == CONTEXT
    assert detail["resolution_source_url"] == "https://ligamx.net/cancha/resultados"

    listing = await client.get("/api/markets", params={"subcategory": "Liga MX"})
    assert listing.status_code == 200
    row = {r["id"]: r for r in listing.json()}["rc-set"]
    assert "rules" not in row and "context" not in row


@pytest.mark.asyncio
async def test_create_market_accepts_rules_context(client, db):
    admin = User(email=ADMIN_EMAIL, username="admin_rc", display_name="Admin", email_verified=True, points=0)
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    payload = {
        "id": "rc-created",
        "question": "¿Se crea con normas?",
        "description": "desc",
        "category": "Deportes",
        "subcategory": "Liga MX",
        "resolution_criteria": "Prueba",
        "resolution_source_url": "https://ligamx.net/cancha/resultados",
        "rules": RULES,
        "context": CONTEXT,
        "ends_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
    }
    resp = await client.post("/api/markets", json=payload, headers=auth_headers(admin))
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["rules"] == RULES
    assert body["context"] == CONTEXT
