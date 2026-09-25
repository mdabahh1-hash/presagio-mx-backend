"""POST /auth/resend-code: código nuevo para una cuenta sin verificar."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import select

from app.models.user import User


async def _unverified(db, emitido_hace: timedelta) -> User:
    u = User(
        email="nuevo@test.local", username="nuevo", display_name="Nuevo",
        email_verified=False, email_verification_code="111111",
        email_verification_expires=datetime.now(timezone.utc) + timedelta(minutes=15) - emitido_hace,
        email_verification_attempts=5, points=0,
    )
    db.add(u)
    await db.commit()
    return u


async def test_resend_rota_codigo_y_resetea_intentos(client, db):
    await _unverified(db, emitido_hace=timedelta(minutes=2))
    with patch("app.api.auth.send_verification_email") as send:
        r = await client.post("/api/auth/resend-code", json={"email": "Nuevo@test.local"})
    assert r.status_code == 200
    u = (await db.execute(select(User).where(User.email == "nuevo@test.local").execution_options(populate_existing=True))).scalar_one()
    assert u.email_verification_code != "111111"
    assert u.email_verification_attempts == 0
    assert send.call_args.args[2] == u.email_verification_code


async def test_resend_espera_un_minuto(client, db):
    await _unverified(db, emitido_hace=timedelta(seconds=10))
    with patch("app.api.auth.send_verification_email") as send:
        r = await client.post("/api/auth/resend-code", json={"email": "nuevo@test.local"})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "RESEND_TOO_SOON"
    send.assert_not_called()


async def test_resend_no_revela_si_existe(client, make_user):
    await make_user("verificado")  # verificado: no se manda nada
    with patch("app.api.auth.send_verification_email") as send:
        a = await client.post("/api/auth/resend-code", json={"email": "verificado@test.local"})
        b = await client.post("/api/auth/resend-code", json={"email": "nadie@test.local"})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    send.assert_not_called()
