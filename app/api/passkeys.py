"""WebAuthn passkeys: register from an authenticated session, then log in with
a discoverable credential (Face ID / Touch ID / security key).
"""
import json
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from pydantic import BaseModel

from app.config import settings
from app.core.auth import get_current_user, create_access_token
from app.database import get_db
from app.models.passkey import Passkey
from app.models.user import User
from app.schemas.user import UserMe

router = APIRouter(prefix="/auth/passkey", tags=["passkeys"])

# ── In-memory challenge store ────────────────────────────────────────────────
# Single uvicorn process on Railway (same precedent as the proposals rate
# limiter); would need a shared store under multiple workers. Challenges are
# single-use and expire after 2 minutes.
_CHALLENGE_TTL = 120.0
_challenges: dict[str, tuple[bytes, int | None, float]] = {}


def _put_challenge(challenge: bytes, user_id: int | None) -> str:
    now = time.monotonic()
    # prune expired entries
    for k in [k for k, (_, _, exp) in _challenges.items() if exp < now]:
        del _challenges[k]
    state = secrets.token_urlsafe(24)
    _challenges[state] = (challenge, user_id, now + _CHALLENGE_TTL)
    return state


def _pop_challenge(state: str) -> tuple[bytes, int | None] | None:
    entry = _challenges.pop(state, None)
    if entry is None:
        return None
    challenge, user_id, exp = entry
    if exp < time.monotonic():
        return None
    return challenge, user_id


def _rp_for_request(request: Request) -> tuple[str, list[str]]:
    """(rp_id, expected_origins) for this request.

    Selecting by the Origin header is NOT a security hole: it only chooses
    which pair py_webauthn will ENFORCE — verification then checks the
    browser-signed clientDataJSON.origin and the authenticator's rpIdHash
    against exactly that pair, so a spoofed header buys nothing.
    Localhost support makes local dev work with zero env changes.
    """
    origin = request.headers.get("origin", "")
    if origin.startswith("http://localhost"):
        return "localhost", [origin]
    return settings.WEBAUTHN_RP_ID, [f"https://{settings.WEBAUTHN_RP_ID}", settings.FRONTEND_URL]


class PasskeyVerifyRequest(BaseModel):
    state: str
    credential: dict


@router.post("/register/options")
async def passkey_register_options(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rp_id, _ = _rp_for_request(request)
    existing = (await db.execute(
        select(Passkey).where(Passkey.user_id == current_user.id)
    )).scalars().all()

    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(current_user.id).encode(),
        user_name=current_user.email,
        user_display_name=current_user.display_name,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(pk.credential_id)) for pk in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,  # discoverable: login sin pedir email
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    state = _put_challenge(options.challenge, current_user.id)
    # options_to_json returns a STRING — parse so the response nests an object.
    return {"state": state, "options": json.loads(options_to_json(options))}


@router.post("/register/verify")
async def passkey_register_verify(
    payload: PasskeyVerifyRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    popped = _pop_challenge(payload.state)
    if popped is None or popped[1] != current_user.id:
        raise HTTPException(status_code=400, detail={"code": "PASSKEY_SESSION_EXPIRED", "message": "Sesión de passkey expirada, intenta de nuevo"})
    challenge, _ = popped

    rp_id, origins = _rp_for_request(request)
    try:
        verification = verify_registration_response(
            credential=payload.credential,
            expected_challenge=challenge,
            expected_origin=origins,
            expected_rp_id=rp_id,
        )
    except Exception:
        raise HTTPException(status_code=400, detail={"code": "PASSKEY_VERIFY_FAILED", "message": "No se pudo verificar la passkey"})

    credential_id = bytes_to_base64url(verification.credential_id)
    dup = (await db.execute(
        select(Passkey.id).where(Passkey.credential_id == credential_id)
    )).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status_code=409, detail={"code": "PASSKEY_ALREADY_REGISTERED", "message": "Esta passkey ya está registrada"})

    transports = payload.credential.get("response", {}).get("transports") or []
    db.add(Passkey(
        user_id=current_user.id,
        credential_id=credential_id,
        public_key=bytes_to_base64url(verification.credential_public_key),
        sign_count=verification.sign_count,
        transports=",".join(transports) or None,
    ))
    await db.commit()
    return {"ok": True, "message": "Passkey agregada"}


@router.post("/login/options")
async def passkey_login_options(request: Request):
    rp_id, _ = _rp_for_request(request)
    # Empty allow_credentials → discoverable/resident flow (no email needed).
    options = generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    state = _put_challenge(options.challenge, None)
    return {"state": state, "options": json.loads(options_to_json(options))}


@router.post("/login/verify")
async def passkey_login_verify(
    payload: PasskeyVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    popped = _pop_challenge(payload.state)
    if popped is None:
        raise HTTPException(status_code=400, detail={"code": "PASSKEY_SESSION_EXPIRED", "message": "Sesión de passkey expirada, intenta de nuevo"})
    challenge, _ = popped

    credential_id = payload.credential.get("id", "")
    pk = (await db.execute(
        select(Passkey).where(Passkey.credential_id == credential_id)
    )).scalar_one_or_none()
    if pk is None:
        raise HTTPException(status_code=401, detail={"code": "PASSKEY_NOT_RECOGNIZED", "message": "Passkey no reconocida"})

    rp_id, origins = _rp_for_request(request)
    try:
        verification = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origins,
            credential_public_key=base64url_to_bytes(pk.public_key),
            credential_current_sign_count=pk.sign_count,
            require_user_verification=False,
        )
    except Exception:
        raise HTTPException(status_code=401, detail={"code": "PASSKEY_VERIFY_FAILED", "message": "No se pudo verificar la passkey"})

    pk.sign_count = verification.new_sign_count
    pk.last_used_at = datetime.now(timezone.utc)

    user = (await db.execute(select(User).where(User.id == pk.user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail={"code": "PASSKEY_NOT_RECOGNIZED", "message": "Passkey no reconocida"})
    await db.commit()

    # No email_verified check needed: registering a passkey required an
    # authenticated session in the first place. Same response shape as /auth/login.
    token = create_access_token(str(user.id))
    me = UserMe.model_validate(user)
    me.has_passkey = True
    return {"token": token, "user": me}


@router.delete("")
async def passkey_delete_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(Passkey).where(Passkey.user_id == current_user.id)
    )).scalars().all()
    for pk in rows:
        await db.delete(pk)
    await db.commit()
    return {"ok": True}
