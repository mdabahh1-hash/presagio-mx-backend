"""OAuth signup regression tests + signed `state` (anti-CSRF, `next`).

Production incident 2026-09-05: a new Google user got a plain-text 500 because
Google returned a ~1,000-char profile-picture URL and users.avatar_url was
VARCHAR(500). These tests pin the fix (column is TEXT) and the hardened
callback (any failure redirects back to the app instead of 500ing).

Since 2026-09-09 the start endpoints mint a signed `state` JWT (provider,
nonce, `next` route, 10-min expiry) and set the nonce in an `oauth_nonce`
cookie; callbacks reject a missing/invalid state and echo `next` back to the
SPA so the user lands where they started (league invite, market…).
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from jose import jwt as jose_jwt
from sqlalchemy import select, text

from app.api.auth import get_or_create_user
from app.config import settings
from app.core.auth import ALGORITHM
from app.models.user import User
from tests.conftest import app_db

# Realistic shape: Google's lh3 URLs are long opaque tokens ending in "=s96-c".
LONG_AVATAR = "https://lh3.googleusercontent.com/a-/" + ("A" * 1100) + "=s96-c"


# ── helpers de state ──────────────────────────────────────────────────────────

def _query(url: str) -> dict[str, str]:
    """Query params de una URL; para las del SPA (`/#/auth/callback?…`) usa el fragmento."""
    parsed = urlparse(url)
    raw = parsed.fragment.split("?", 1)[1] if parsed.fragment and "?" in parsed.fragment else parsed.query
    return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}


def _decode_state(location: str) -> dict:
    return jose_jwt.decode(_query(location)["state"], settings.SECRET_KEY, algorithms=[ALGORITHM])


def _mint_state(provider: str, next: str | None = None, nonce: str = "n1", exp_delta: int = 300,
                key: str | None = None, typ: str = "oauth_state") -> str:
    now = datetime.now(timezone.utc)
    payload = {"typ": typ, "p": provider, "n": nonce, "next": next,
               "iat": now, "exp": now + timedelta(seconds=exp_delta)}
    return jose_jwt.encode(payload, key or settings.SECRET_KEY, algorithm=ALGORITHM)


class _OkResp:
    is_success = True
    status_code = 200
    text = ""

    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _fake_ok_client(userinfo: dict):
    """httpx.AsyncClient falso: el token exchange y el userinfo responden OK."""

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            return _OkResp({"access_token": "fake-access-token"})

        async def get(self, *a, **kw):
            return _OkResp(userinfo)

    return _FakeClient


GOOGLE_INFO = {"sub": "g-123", "email": "nuevo@gmail.com", "name": "Nuevo Google", "picture": None}
GITHUB_INFO = {"id": 77, "login": "octo", "email": "octo@github.com", "name": "Octo", "avatar_url": None}


@pytest.mark.asyncio
async def test_new_google_user_with_long_avatar_url(db):
    user = await get_or_create_user(
        db,
        email="nuevo@gmail.com",
        display_name="Daniel Zaga",
        avatar_url=LONG_AVATAR,
        provider="google",
        provider_id="109873255256130498679",
    )
    assert user.id is not None
    assert user.username == "daniel_zaga"
    assert user.google_id == "109873255256130498679"
    assert user.referral_code

    stored = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    assert stored.avatar_url == LONG_AVATAR
    assert len(stored.avatar_url) > 500


@pytest.mark.asyncio
async def test_existing_email_user_gets_google_id_and_long_avatar(db, make_user):
    existing = await make_user("veterano")
    # make_user uses <username>@test.local
    user = await get_or_create_user(
        db,
        email=existing.email,
        display_name="Veterano Google",
        avatar_url=LONG_AVATAR,
        provider="google",
        provider_id="g-veterano",
    )
    assert user.id == existing.id
    assert user.google_id == "g-veterano"
    assert user.avatar_url == LONG_AVATAR


@pytest.mark.asyncio
async def test_avatar_url_column_is_text():
    async with app_db.engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'avatar_url'"
        ))
        assert res.scalar_one() == "text"


@pytest.mark.asyncio
async def test_google_callback_failure_redirects_instead_of_500(client):
    """Any exception inside the callback must become a redirect to the SPA
    with ?error=oauth_failed, never Starlette's plain-text 500."""

    class _FakeResp:
        is_success = False
        status_code = 400
        text = "invalid_grant"

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            return _FakeResp()

    with patch("app.api.auth.httpx.AsyncClient", _FakeClient):
        resp = await client.get(
            "/api/auth/google/callback",
            params={"code": "bad", "state": _mint_state("google", next="/l/abc?join=1")},
            follow_redirects=False,
        )

    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "#/auth/callback?error=oauth_failed" in location
    assert "provider=google" in location
    assert "token=" not in location
    # El fallo del proveedor conserva `next` para que el usuario pueda reintentar donde estaba.
    assert _query(location)["next"] == "/l/abc?join=1"


# ── state firmado: endpoints de inicio ───────────────────────────────────────

@pytest.mark.asyncio
async def test_google_login_redirect_carries_signed_state_and_next(client):
    resp = await client.get("/api/auth/google", params={"next": "/l/abc?join=1"}, follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert urlparse(location).netloc == "accounts.google.com"

    payload = _decode_state(location)
    assert payload["typ"] == "oauth_state"
    assert payload["p"] == "google"
    assert payload["next"] == "/l/abc?join=1"
    assert payload["n"]

    set_cookie = resp.headers["set-cookie"]
    assert f"oauth_nonce={payload['n']}" in set_cookie
    assert "Path=/api/auth" in set_cookie
    assert "HttpOnly" in set_cookie


@pytest.mark.asyncio
async def test_github_login_redirect_carries_signed_state(client):
    resp = await client.get("/api/auth/github", follow_redirects=False)
    location = resp.headers["location"]
    assert urlparse(location).netloc == "github.com"
    payload = _decode_state(location)
    assert payload["p"] == "github"
    assert payload["next"] is None
    assert "oauth_nonce=" in resp.headers["set-cookie"]


@pytest.mark.parametrize("bad_next", [
    "https://evil.com",
    "//evil.com",
    "/\\evil.com",
    "/a#b",
    "javascript:alert(1)",
    "/auth/callback?token=x",
    "/" + "a" * 300,
    "/con espacio",
])
@pytest.mark.asyncio
async def test_login_drops_unsafe_next(client, bad_next):
    resp = await client.get("/api/auth/google", params={"next": bad_next}, follow_redirects=False)
    assert _decode_state(resp.headers["location"])["next"] is None


# ── state firmado: callbacks ─────────────────────────────────────────────────

def _assert_rejected(location: str, provider: str):
    q = _query(location)
    assert q["error"] == "oauth_state_invalid"
    assert q["provider"] == provider
    assert "token" not in q


@pytest.mark.asyncio
async def test_callback_missing_state_rejected(client):
    resp = await client.get("/api/auth/google/callback?code=abc", follow_redirects=False)
    assert resp.status_code in (302, 307)
    _assert_rejected(resp.headers["location"], "google")


@pytest.mark.asyncio
async def test_callback_tampered_state_rejected(client):
    bad = _mint_state("google", key="another-secret-key-0123456789abcdef0123456789")
    resp = await client.get("/api/auth/google/callback", params={"code": "abc", "state": bad}, follow_redirects=False)
    _assert_rejected(resp.headers["location"], "google")


@pytest.mark.asyncio
async def test_callback_expired_state_rejected(client):
    old = _mint_state("google", exp_delta=-60)
    resp = await client.get("/api/auth/google/callback", params={"code": "abc", "state": old}, follow_redirects=False)
    _assert_rejected(resp.headers["location"], "google")


@pytest.mark.asyncio
async def test_callback_wrong_typ_rejected(client):
    # Un access token normal (sub/exp) firmado con la misma clave no sirve como state.
    other = _mint_state("google", typ="access")
    resp = await client.get("/api/auth/google/callback", params={"code": "abc", "state": other}, follow_redirects=False)
    _assert_rejected(resp.headers["location"], "google")


@pytest.mark.asyncio
async def test_callback_provider_mismatch_rejected(client):
    google_state = _mint_state("google")
    resp = await client.get("/api/auth/github/callback", params={"code": "abc", "state": google_state}, follow_redirects=False)
    _assert_rejected(resp.headers["location"], "github")


@pytest.mark.asyncio
async def test_callback_nonce_cookie_mismatch_rejected(client):
    resp = await client.get(
        "/api/auth/google/callback",
        params={"code": "abc", "state": _mint_state("google", nonce="n1")},
        cookies={"oauth_nonce": "other"},
        follow_redirects=False,
    )
    _assert_rejected(resp.headers["location"], "google")


@pytest.mark.asyncio
async def test_callback_require_cookie_flag_rejects_without_cookie(client):
    with patch.object(settings, "OAUTH_STATE_REQUIRE_COOKIE", True):
        resp = await client.get(
            "/api/auth/google/callback",
            params={"code": "abc", "state": _mint_state("google")},
            follow_redirects=False,
        )
    _assert_rejected(resp.headers["location"], "google")


@pytest.mark.asyncio
async def test_callback_without_code_redirects_as_denied(client):
    # Google manda ?error=access_denied sin code cuando el usuario cancela: antes era un 422 JSON.
    resp = await client.get(
        "/api/auth/google/callback",
        params={"error": "access_denied", "state": _mint_state("google", next="/mercado/7")},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    q = _query(resp.headers["location"])
    assert q["error"] == "oauth_denied"
    assert q["next"] == "/mercado/7"


@pytest.mark.asyncio
async def test_google_callback_happy_path_without_cookie_keeps_next(client, db):
    """Navegador in-app → Safari: no hay cookie, pero el state firmado basta (modo laxo)."""
    with patch("app.api.auth.httpx.AsyncClient", _fake_ok_client(GOOGLE_INFO)):
        resp = await client.get(
            "/api/auth/google/callback",
            params={"code": "ok", "state": _mint_state("google", next="/l/abc?join=1")},
            follow_redirects=False,
        )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "#/auth/callback?" in location
    q = _query(location)
    assert q["token"]
    assert q["next"] == "/l/abc?join=1"
    assert "next=%2Fl%2Fabc%3Fjoin%3D1" in location
    assert "access_token=" in resp.headers["set-cookie"]

    user = (await db.execute(select(User).where(User.email == "nuevo@gmail.com"))).scalar_one()
    assert user.google_id == "g-123"


@pytest.mark.asyncio
async def test_google_callback_happy_path_with_matching_cookie(client):
    with patch("app.api.auth.httpx.AsyncClient", _fake_ok_client(GOOGLE_INFO)):
        resp = await client.get(
            "/api/auth/google/callback",
            params={"code": "ok", "state": _mint_state("google", nonce="n1")},
            cookies={"oauth_nonce": "n1"},
            follow_redirects=False,
        )
    q = _query(resp.headers["location"])
    assert q["token"]
    assert "next" not in q
    # La cookie de nonce es de un solo uso: el callback la borra.
    assert "oauth_nonce=" in resp.headers["set-cookie"]
    assert 'oauth_nonce=""' in resp.headers["set-cookie"] or "oauth_nonce=;" in resp.headers["set-cookie"]


@pytest.mark.asyncio
async def test_github_callback_happy_path(client, db):
    with patch("app.api.auth.httpx.AsyncClient", _fake_ok_client(GITHUB_INFO)):
        resp = await client.get(
            "/api/auth/github/callback",
            params={"code": "ok", "state": _mint_state("github", next="/perfil")},
            follow_redirects=False,
        )
    q = _query(resp.headers["location"])
    assert q["token"]
    assert q["next"] == "/perfil"
    user = (await db.execute(select(User).where(User.email == "octo@github.com"))).scalar_one()
    assert user.github_id == "77"
