"""Tests for WebAuthn passkey endpoints.

The options endpoints exercise real py_webauthn. The verify endpoints
monkeypatch the library's verify functions (a real authenticator cannot run in
CI); what we test is OUR logic: challenge lifecycle, persistence, token
issuance and error paths.
"""
import time
from types import SimpleNamespace

import pytest

import app.api.passkeys as pk_mod
from sqlalchemy import select

from tests.conftest import auth_headers
from app.models.passkey import Passkey


@pytest.fixture(autouse=True)
def _clear_challenges():
    pk_mod._challenges.clear()
    yield
    pk_mod._challenges.clear()


async def test_register_options_shape(client, make_user):
    user = await make_user("pk_reg_opts")
    resp = await client.post("/api/auth/passkey/register/options", headers=auth_headers(user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] in pk_mod._challenges
    opts = body["options"]
    assert opts["challenge"]
    assert opts["rp"]["id"] == "veredikt.mx"  # no Origin header → prod RP
    assert opts["user"]["name"] == user.email
    assert opts["authenticatorSelection"]["residentKey"] == "required"


async def test_register_options_localhost_origin(client, make_user):
    user = await make_user("pk_localhost")
    resp = await client.post(
        "/api/auth/passkey/register/options",
        headers={**auth_headers(user), "Origin": "http://localhost:5173"},
    )
    assert resp.json()["options"]["rp"]["id"] == "localhost"


async def test_register_options_requires_auth(client):
    assert (await client.post("/api/auth/passkey/register/options")).status_code == 401


async def test_login_options_public_and_discoverable(client):
    resp = await client.post("/api/auth/passkey/login/options")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] in pk_mod._challenges
    assert body["options"]["challenge"]
    # discoverable flow: no allowCredentials restriction
    assert not body["options"].get("allowCredentials")


def _stub_registration(credential_id: bytes = b"cred-1", public_key: bytes = b"pubkey-1", sign_count: int = 0):
    return SimpleNamespace(credential_id=credential_id, credential_public_key=public_key, sign_count=sign_count)


async def test_register_verify_saves_passkey_and_flips_flag(client, db, make_user, monkeypatch):
    user = await make_user("pk_verify")
    headers = auth_headers(user)
    state = (await client.post("/api/auth/passkey/register/options", headers=headers)).json()["state"]

    monkeypatch.setattr(pk_mod, "verify_registration_response", lambda **kw: _stub_registration())
    resp = await client.post(
        "/api/auth/passkey/register/verify",
        json={"state": state, "credential": {"id": "x", "response": {"transports": ["internal"]}}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    rows = (await db.execute(select(Passkey))).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == user.id
    assert rows[0].transports == "internal"

    me = (await client.get("/api/users/me", headers=headers)).json()
    assert me["has_passkey"] is True
    assert "password_hash" not in me


async def test_register_verify_bad_state(client, make_user):
    user = await make_user("pk_badstate")
    resp = await client.post(
        "/api/auth/passkey/register/verify",
        json={"state": "nope", "credential": {}},
        headers=auth_headers(user),
    )
    assert resp.status_code == 400
    assert "expirada" in resp.json()["detail"]


async def test_register_verify_expired_state(client, make_user):
    user = await make_user("pk_expired")
    headers = auth_headers(user)
    state = (await client.post("/api/auth/passkey/register/options", headers=headers)).json()["state"]
    # rewind the expiry
    ch, uid, _ = pk_mod._challenges[state]
    pk_mod._challenges[state] = (ch, uid, time.monotonic() - 1)
    resp = await client.post(
        "/api/auth/passkey/register/verify",
        json={"state": state, "credential": {}},
        headers=headers,
    )
    assert resp.status_code == 400


async def _seed_passkey(db, user, credential_id="cred-b64u", public_key="pub-b64u", sign_count=5):
    row = Passkey(user_id=user.id, credential_id=credential_id, public_key=public_key, sign_count=sign_count)
    db.add(row)
    await db.commit()
    return row


async def test_login_verify_issues_working_token(client, db, make_user, monkeypatch):
    user = await make_user("pk_login")
    # public_key must be valid base64url for base64url_to_bytes
    await _seed_passkey(db, user, credential_id="Y3JlZDE", public_key="cHVi", sign_count=5)
    state = (await client.post("/api/auth/passkey/login/options")).json()["state"]

    monkeypatch.setattr(pk_mod, "verify_authentication_response", lambda **kw: SimpleNamespace(new_sign_count=6))
    resp = await client.post(
        "/api/auth/passkey/login/verify",
        json={"state": state, "credential": {"id": "Y3JlZDE"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["username"] == user.username
    assert body["user"]["has_passkey"] is True
    assert "password_hash" not in body["user"]

    # token works
    me = await client.get("/api/users/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == user.id

    # sign_count + last_used_at updated
    row = (await db.execute(
        select(Passkey).where(Passkey.credential_id == "Y3JlZDE").execution_options(populate_existing=True)
    )).scalar_one()
    assert row.sign_count == 6
    assert row.last_used_at is not None


async def test_login_verify_unknown_credential(client):
    state = (await client.post("/api/auth/passkey/login/options")).json()["state"]
    resp = await client.post(
        "/api/auth/passkey/login/verify",
        json={"state": state, "credential": {"id": "desconocida"}},
    )
    assert resp.status_code == 401
    assert "no reconocida" in resp.json()["detail"]


async def test_login_verify_bad_state(client):
    resp = await client.post(
        "/api/auth/passkey/login/verify",
        json={"state": "nope", "credential": {"id": "x"}},
    )
    assert resp.status_code == 400


async def test_delete_removes_passkeys(client, db, make_user):
    user = await make_user("pk_delete")
    await _seed_passkey(db, user)
    headers = auth_headers(user)
    assert (await client.get("/api/users/me", headers=headers)).json()["has_passkey"] is True

    resp = await client.request("DELETE", "/api/auth/passkey", headers=headers)
    assert resp.status_code == 200
    assert (await db.execute(select(Passkey))).scalars().all() == []
    assert (await client.get("/api/users/me", headers=headers)).json()["has_passkey"] is False


async def test_login_response_no_longer_leaks_hash(client, db, make_user):
    """Regression for the pre-existing leak: /auth/login serialized the raw ORM
    user, exposing password_hash and the email verification code."""
    from app.api.auth import _hash_password
    user = await make_user("pk_leak")
    user.password_hash = _hash_password("supersecreta123")
    await db.commit()

    resp = await client.post("/api/auth/login", json={"email": user.email, "password": "supersecreta123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "password_hash" not in body["user"]
    assert "email_verification_code" not in body["user"]
