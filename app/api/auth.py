import logging
import re
import secrets
import string
import httpx
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
import bcrypt as _bcrypt
from jose import JWTError, jwt as jose_jwt
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.core.auth import ALGORITHM, create_access_token
from app.config import settings
from app.schemas.user import UserMe
from app.services.email import send_verification_email
from app.services import referral
from app.core.background import spawn

logger = logging.getLogger(__name__)

# OAuth callbacks are top-level browser navigations: any exception must end in a
# redirect back to the app, never in Starlette's plain-text "Internal Server Error".
OAUTH_HTTP_TIMEOUT = 15.0

# ── OAuth `state` ─────────────────────────────────────────────────────────────
# El state es un JWT firmado con SECRET_KEY, de vida corta, ligado al proveedor
# y con un nonce. El mismo nonce va en la cookie `oauth_nonce`: si la cookie
# vuelve con el callback debe coincidir (anti login-CSRF). Si no vuelve — el
# link se abrió en el navegador in-app de WhatsApp/Instagram y Google saltó a
# Safari — aceptamos el state firmado (ver settings.OAUTH_STATE_REQUIRE_COOKIE).
# El state también transporta `next`: la ruta hash del SPA a la que volver
# después del login (p. ej. la invitación a una liga `/l/CODE?join=1`).
OAUTH_NONCE_COOKIE = "oauth_nonce"
OAUTH_NONCE_COOKIE_PATH = "/api/auth"
OAUTH_NEXT_MAX_LEN = 200
# Caracteres URL imprimibles; sin '#', '\' ni espacios/control.
_NEXT_ALLOWED = re.compile(r"^[A-Za-z0-9\-._~!$&'()*+,;=:@/?%]+$")


def _safe_next(path: str | None) -> str | None:
    """Ruta hash relativa del SPA ('/l/abc?join=1') o None si falta o no es segura."""
    if not path or len(path) > OAUTH_NEXT_MAX_LEN:
        return None
    if not path.startswith("/") or path.startswith("//") or path.startswith("/\\"):
        return None
    if path.startswith("/auth/callback"):
        return None  # nunca volver a entrar al propio callback
    if not _NEXT_ALLOWED.match(path):
        return None
    return path


def _make_oauth_state(provider: str, next_path: str | None) -> tuple[str, str]:
    """Devuelve (state_jwt, nonce)."""
    nonce = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    payload = {
        "typ": "oauth_state",
        "p": provider,
        "n": nonce,
        "next": next_path,
        "iat": now,
        "exp": now + timedelta(seconds=settings.OAUTH_STATE_TTL_SECONDS),
    }
    return jose_jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM), nonce


def _verify_oauth_state(state: str | None, provider: str, cookie_nonce: str | None) -> dict | None:
    """Payload decodificado si el state es válido para este proveedor (y coincide
    con la cookie cuando la hay); None si hay que rechazar el callback."""
    if not state:
        return None
    try:
        payload = jose_jwt.decode(state, settings.SECRET_KEY, algorithms=[ALGORITHM])  # valida exp
    except JWTError:
        return None
    nonce = payload.get("n")
    if payload.get("typ") != "oauth_state" or payload.get("p") != provider or not isinstance(nonce, str) or not nonce:
        return None
    if cookie_nonce is not None:
        if not secrets.compare_digest(cookie_nonce, nonce):
            return None
    elif settings.OAUTH_STATE_REQUIRE_COOKIE:
        return None
    else:
        logger.warning("OAuth %s: state aceptado sin cookie de nonce (¿cambio de navegador?)", provider)
    # Re-validar: el claim viene firmado por nosotros, pero nunca navegar a ciegas.
    payload["next"] = _safe_next(payload.get("next"))
    return payload


def _start_oauth_redirect(url: str, nonce: str) -> RedirectResponse:
    resp = RedirectResponse(url)
    resp.set_cookie(
        OAUTH_NONCE_COOKIE, nonce, httponly=True, secure=True, samesite="lax",
        max_age=settings.OAUTH_STATE_TTL_SECONDS, path=OAUTH_NONCE_COOKIE_PATH,
    )
    return resp


def _callback_redirect(query: dict[str, str]) -> RedirectResponse:
    resp = RedirectResponse(f"{settings.FRONTEND_URL}/#/auth/callback?{urlencode(query)}")
    resp.delete_cookie(OAUTH_NONCE_COOKIE, path=OAUTH_NONCE_COOKIE_PATH)
    return resp


def _oauth_success_redirect(user: User, next_path: str | None = None) -> RedirectResponse:
    jwt_token = create_access_token(user.id)
    query = {"token": jwt_token}
    if next_path:
        query["next"] = next_path
    response = _callback_redirect(query)
    response.set_cookie("access_token", jwt_token, httponly=True, secure=True, samesite="lax", max_age=604800)
    return response


def _oauth_error_redirect(provider: str, error: str = "oauth_failed", next_path: str | None = None) -> RedirectResponse:
    if error == "oauth_failed":
        logger.exception("OAuth %s callback failed", provider)  # se llama desde un except
    else:
        logger.warning("OAuth %s rechazado: %s", provider, error)
    query = {"error": error, "provider": provider}
    if next_path:
        query["next"] = next_path
    return _callback_redirect(query)


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

    @field_validator("password")
    @classmethod
    def password_strong_enough(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v


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
    await referral.ensure_code(db, user)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google")
async def google_login(request: Request, next: str | None = Query(None, max_length=512)):
    cb = _callback_url(request, "/api/auth/google/callback")
    state, nonce = _make_oauth_state("google", _safe_next(next))
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": cb,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
    })
    return _start_oauth_redirect(url, nonce)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    oauth_nonce: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    st = _verify_oauth_state(state, "google", oauth_nonce)
    if st is None:
        return _oauth_error_redirect("google", error="oauth_state_invalid")
    next_path = st["next"]
    if not code:  # el usuario canceló en Google (?error=access_denied)
        return _oauth_error_redirect("google", error="oauth_denied", next_path=next_path)
    cb = _callback_url(request, "/api/auth/google/callback")
    try:
        async with httpx.AsyncClient(timeout=OAUTH_HTTP_TIMEOUT) as client:
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
                raise RuntimeError(f"Google token error {token_resp.status_code}: {token_resp.text}")
            access_token = token_resp.json()["access_token"]

            user_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_resp.raise_for_status()
            info = user_resp.json()

        email = info["email"]
        user = await get_or_create_user(
            db,
            email=email,
            display_name=info.get("name") or email,
            avatar_url=info.get("picture"),
            provider="google",
            provider_id=info["sub"],
        )
    except Exception:
        return _oauth_error_redirect("google", next_path=next_path)
    return _oauth_success_redirect(user, next_path)


# ── GitHub OAuth ──────────────────────────────────────────────────────────────

@router.get("/github")
async def github_login(request: Request, next: str | None = Query(None, max_length=512)):
    cb = _callback_url(request, "/api/auth/github/callback")
    state, nonce = _make_oauth_state("github", _safe_next(next))
    url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": cb,
        "scope": "user:email",
        "state": state,
    })
    return _start_oauth_redirect(url, nonce)


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    oauth_nonce: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    st = _verify_oauth_state(state, "github", oauth_nonce)
    if st is None:
        return _oauth_error_redirect("github", error="oauth_state_invalid")
    next_path = st["next"]
    if not code:
        return _oauth_error_redirect("github", error="oauth_denied", next_path=next_path)
    cb = _callback_url(request, "/api/auth/github/callback")
    try:
        async with httpx.AsyncClient(timeout=OAUTH_HTTP_TIMEOUT) as client:
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
    except Exception:
        return _oauth_error_redirect("github", next_path=next_path)
    return _oauth_success_redirect(user, next_path)


@router.post("/register")
async def email_register(payload: EmailRegisterRequest, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail={"code": "EMAIL_ALREADY_REGISTERED", "message": "Este correo ya está registrado"})

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
    await referral.ensure_code(db, user)
    db.add(user)
    await db.commit()

    spawn(send_verification_email(email, payload.display_name.strip(), code))
    return {"message": "Código enviado a tu correo", "email": email}


@router.post("/login")
async def email_login(payload: EmailLoginRequest, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Correo o contraseña incorrectos"})

    if not user.email_verified:
        raise HTTPException(status_code=403, detail={"code": "EMAIL_NOT_VERIFIED", "message": "Verifica tu correo antes de entrar"})

    token = create_access_token(user.id)
    # UserMe (not the raw ORM object): the raw object would serialize
    # password_hash and the verification code into the response.
    return {"token": token, "user": UserMe.model_validate(user)}


@router.post("/verify-email")
async def verify_email_endpoint(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    email = payload.email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "Usuario no encontrado"})

    if user.email_verified:
        # Ya verificado: nunca emitir token aquí — este endpoint no valida
        # contraseña, así que devolver un JWT permitiría suplantar a cualquier
        # usuario verificado conociendo solo su correo.
        raise HTTPException(status_code=400, detail={"code": "ALREADY_VERIFIED", "message": "Este correo ya está verificado. Inicia sesión."})

    # Brute-force guard: after too many wrong tries, invalidate the code (forces resend).
    if (user.email_verification_attempts or 0) >= 5:
        user.email_verification_code = None
        user.email_verification_expires = None
        await db.commit()
        raise HTTPException(status_code=429, detail={"code": "TOO_MANY_ATTEMPTS", "message": "Demasiados intentos. Solicita un código nuevo."})

    code_ok = bool(user.email_verification_code) and secrets.compare_digest(
        user.email_verification_code, payload.code.strip()
    )
    expired = not user.email_verification_expires or datetime.now(timezone.utc) > user.email_verification_expires
    if not code_ok or expired:
        user.email_verification_attempts = (user.email_verification_attempts or 0) + 1
        await db.commit()
        raise HTTPException(status_code=400, detail={"code": "INVALID_CODE", "message": "Código inválido o expirado"})

    user.email_verified = True
    user.email_verification_code = None
    user.email_verification_expires = None
    user.email_verification_attempts = 0
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return {"token": token, "user": UserMe.model_validate(user)}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}
