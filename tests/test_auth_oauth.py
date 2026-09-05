"""OAuth signup regression tests.

Production incident 2026-09-05: a new Google user got a plain-text 500 because
Google returned a ~1,000-char profile-picture URL and users.avatar_url was
VARCHAR(500). These tests pin the fix (column is TEXT) and the hardened
callback (any failure redirects back to the app instead of 500ing).
"""
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from app.api.auth import get_or_create_user
from app.models.user import User
from tests.conftest import app_db

# Realistic shape: Google's lh3 URLs are long opaque tokens ending in "=s96-c".
LONG_AVATAR = "https://lh3.googleusercontent.com/a-/" + ("A" * 1100) + "=s96-c"


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
        resp = await client.get("/api/auth/google/callback?code=bad", follow_redirects=False)

    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "#/auth/callback?error=oauth_failed" in location
    assert "provider=google" in location
    assert "token=" not in location
