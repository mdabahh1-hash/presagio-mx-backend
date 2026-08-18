"""Tests for POST /api/proposals (public market suggestions)."""
import pytest
import pytest_asyncio
from sqlalchemy import select, func as safunc

import app.api.proposals as proposals_mod
from app.models.market_proposal import MarketProposal


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    # The module-level rate-limit dict persists across tests in one pytest
    # process; clear it so each test starts with a clean window.
    proposals_mod._recent.clear()
    yield
    proposals_mod._recent.clear()


VALID = {
    "question": "¿Ganará México la Copa Oro 2027?",
    "category": "Otro",
    "description": "Se resuelve con el resultado oficial de CONCACAF.",
    "proposer_contact": "fan@correo.mx",
}


async def test_valid_proposal_saved_and_thanked(client, db):
    resp = await client.post("/api/proposals", json=VALID)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert "Gracias" in body["message"]

    res = await db.execute(select(MarketProposal))
    rows = res.scalars().all()
    assert len(rows) == 1
    p = rows[0]
    assert p.question == VALID["question"]
    assert p.category == "Otro"
    assert p.description == VALID["description"]
    assert p.proposer_contact == VALID["proposer_contact"]
    assert p.status == "pending"
    assert p.created_at is not None


async def test_minimal_proposal_ok(client, db):
    resp = await client.post("/api/proposals", json={"question": "¿Sube el dólar mañana?", "category": "Banxico"})
    assert resp.status_code == 201
    res = await db.execute(select(MarketProposal))
    p = res.scalars().one()
    assert p.description is None
    assert p.proposer_contact is None


async def test_question_too_long_rejected(client, db):
    resp = await client.post("/api/proposals", json={**VALID, "question": "x" * 201})
    assert resp.status_code == 422
    count = (await db.execute(select(safunc.count()).select_from(MarketProposal))).scalar_one()
    assert count == 0


async def test_empty_question_rejected(client):
    assert (await client.post("/api/proposals", json={**VALID, "question": "   "})).status_code == 422
    assert (await client.post("/api/proposals", json={"category": "Otro"})).status_code == 422


async def test_category_free_text_roundtrip(client, db):
    resp = await client.post("/api/proposals", json={"question": "¿Pregunta libre?", "category": "Liga MX"})
    assert resp.status_code == 201
    p = (await db.execute(select(MarketProposal))).scalars().one()
    assert p.category == "Liga MX"


async def test_rate_limit_5_per_ip_per_hour(client):
    headers = {"X-Forwarded-For": "203.0.113.7"}
    for i in range(5):
        resp = await client.post("/api/proposals", json={**VALID, "question": f"¿Propuesta {i}?"}, headers=headers)
        assert resp.status_code == 201, f"proposal {i}: {resp.text}"
    resp = await client.post("/api/proposals", json={**VALID, "question": "¿La sexta?"}, headers=headers)
    assert resp.status_code == 429
    assert "Demasiadas propuestas" in resp.json()["detail"]

    # A different IP is unaffected
    resp = await client.post(
        "/api/proposals", json={**VALID, "question": "¿Otra IP?"}, headers={"X-Forwarded-For": "198.51.100.9"}
    )
    assert resp.status_code == 201


async def test_email_failure_does_not_fail_request(client, db, monkeypatch):
    """Even if the notification coroutine blows up, the user gets a 201 and the
    row is already committed."""
    async def boom(*a, **k):
        raise RuntimeError("resend down")

    monkeypatch.setattr(proposals_mod, "send_proposal_notification", boom)
    resp = await client.post("/api/proposals", json={**VALID, "question": "¿Email caído?"})
    assert resp.status_code == 201
    count = (await db.execute(select(safunc.count()).select_from(MarketProposal))).scalar_one()
    assert count == 1
