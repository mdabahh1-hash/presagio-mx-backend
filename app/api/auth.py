import re
import secrets
import string
import httpx
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
import bcrypt as _bcrypt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.core.auth import create_access_token
from app.config import settings
from app.schemas.user import UserMe
from app.services.email import send_verification_email

def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(12)).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode(), hashed.encode())


def _gen_code() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


class EmailRegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str


class EmailLoginRequest(BaseModel):
    email: str
    password: str


class VerifyEmailRequest(BaseModel):
    email: str
    code: str


def _callback_url(request: Request, path: str) -> str:
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://") and "localhost" not in base:
        base = "https://" + base[7:]
    base = re.sub(r":\d+$", "", base)  # strip port injected by Railway proxy
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
        if not token_resp.is_success:
            raise HTTPException(status_code=400, detail=f"Google token error {token_resp.status_code}: {token_resp.text}")
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


@router.post("/register")
async def email_register(payload: EmailRegisterRequest, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Este correo ya está registrado")

    base_username = slugify_username(payload.display_name)
    username = base_username
    suffix = 1
    while True:
        exists = await db.execute(select(User).where(User.username == username))
        if not exists.scalar_one_or_none():
            break
        username = f"{base_username}_{suffix}"
        suffix += 1

    code = _gen_code()
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)

    user = User(
        email=email,
        username=username,
        display_name=payload.display_name.strip(),
        password_hash=_hash_password(payload.password),
        email_verified=False,
        email_verification_code=code,
        email_verification_expires=expires,
        points=float(settings.NEW_USER_POINTS),
    )
    db.add(user)
    await db.commit()

    await send_verification_email(email, payload.display_name.strip(), code)
    return {"message": "Código enviado a tu correo", "email": email}


@router.post("/login")
async def email_login(payload: EmailLoginRequest, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")

    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verifica tu correo antes de entrar")

    token = create_access_token(user.id)
    return {"token": token, "user": user}


@router.post("/verify-email")
async def verify_email_endpoint(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.email_verified:
        token = create_access_token(user.id)
        return {"token": token, "user": user}

    if (
        not user.email_verification_code
        or user.email_verification_code != payload.code.strip()
        or not user.email_verification_expires
        or datetime.now(timezone.utc) > user.email_verification_expires
    ):
        raise HTTPException(status_code=400, detail="Código inválido o expirado")

    user.email_verified = True
    user.email_verification_code = None
    user.email_verification_expires = None
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return {"token": token, "user": user}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}
