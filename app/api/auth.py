import re
import httpx
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.core.auth import create_access_token
from app.config import settings
from app.schemas.user import UserMe


def _callback_url(request: Request, path: str) -> str:
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://") and "localhost" not in base:
        base = "https://" + base[7:]
    return f"{base}{path}"

router = APIRouter(prefix="/auth", tags=["auth"])


def slugify_username(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.lower())[:30]


async def get_or_create_user(
    db: AsyncSession,
    email: str,
    display_name: str,
    avatar_url: str | None,
    provider: str,
    provider_id: str,
) -> User:
    filter_col = User.google_id if provider == "google" else User.github_id
    result = await db.execute(select(User).where(filter_col == provider_id))
    user = result.scalar_one_or_none()

    if not user:
        # Check if email already registered
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if user:
        # Update provider id if missing
        if provider == "google" and not user.google_id:
            user.google_id = provider_id
        elif provider == "github" and not user.github_id:
            user.github_id = provider_id
        if avatar_url:
            user.avatar_url = avatar_url
        await db.commit()
        await db.refresh(user)
        return user

    # Create new user
    base_username = slugify_username(display_name)
    username = base_username
    suffix = 1
    while True:
        exists = await db.execute(select(User).where(User.username == username))
        if not exists.scalar_one_or_none():
            break
        username = f"{base_username}_{suffix}"
        suffix += 1

    user = User(
        email=email,
        username=username,
        display_name=display_name,
        avatar_url=avatar_url,
        points=float(settings.NEW_USER_POINTS),
        google_id=provider_id if provider == "google" else None,
        github_id=provider_id if provider == "github" else None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google")
async def google_login(request: Request):
    cb = _callback_url(request, "/api/auth/google/callback")
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": cb,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    })
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(request: Request, code: str, db: AsyncSession = Depends(get_db)):
    cb = _callback_url(request, "/api/auth/google/callback")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": cb,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        info = user_resp.json()

    user = await get_or_create_user(
        db,
        email=info["email"],
        display_name=info.get("name", info["email"]),
        avatar_url=info.get("picture"),
        provider="google",
        provider_id=info["sub"],
    )
    jwt_token = create_access_token(user.id)
    response = RedirectResponse(f"{settings.FRONTEND_URL}/#/auth/callback?token={jwt_token}")
    response.set_cookie("access_token", jwt_token, httponly=True, samesite="lax", max_age=604800)
    return response


# ── GitHub OAuth ──────────────────────────────────────────────────────────────

@router.get("/github")
async def github_login(request: Request):
    cb = _callback_url(request, "/api/auth/github/callback")
    url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": cb,
        "scope": "user:email",
    })
    return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(request: Request, code: str, db: AsyncSession = Depends(get_db)):
    cb = _callback_url(request, "/api/auth/github/callback")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": cb,
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        gh_user = user_resp.json()

        # Get primary email if not public
        email = gh_user.get("email")
        if not email:
            email_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            emails = email_resp.json()
            primary = next((e for e in emails if e.get("primary")), None)
            email = primary["email"] if primary else f"{gh_user['login']}@github.invalid"

    user = await get_or_create_user(
        db,
        email=email,
        display_name=gh_user.get("name") or gh_user["login"],
        avatar_url=gh_user.get("avatar_url"),
        provider="github",
        provider_id=str(gh_user["id"]),
    )
    jwt_token = create_access_token(user.id)
    response = RedirectResponse(f"{settings.FRONTEND_URL}/#/auth/callback?token={jwt_token}")
    response.set_cookie("access_token", jwt_token, httponly=True, samesite="lax", max_age=604800)
    return response


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}
